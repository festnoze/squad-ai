# pmx v2 - CONTRACTS

**Status: authoritative for code.** `docs/PRD_V2_HARD_OPTIMIZER.md` says what and why;
`docs/PLAN_V2_WAVES.md` says in which order and by whom; this document says how the code is shaped so that
twenty-seven packages can be built in parallel and compose without anyone merging by hand.

If this document and the PRD disagree on a functional point, the PRD wins and this document is amended in
the same commit, with the amendment recorded in section 15. If this document and the code disagree, this
document wins and the code is a bug. If this document and the plan disagree, this document wins for code and
the disagreement is reported as a contract issue for the gate.

Written 2026-09-07 (contract version `2.0`). Every number in this document that a test can pin is a named
constant in `pmx.types`, and the constant, not the prose, is what the code reads.

Rules for every contributor, restated from the plan because they are the ones that get broken:

1. **Never edit a file you do not own.** Ownership is section 13. A change you need in someone else's file
   is a contract issue, reported to the gate, never a silent edit.
2. **Never widen a public signature silently.** The signatures of sections 8 to 12 are literal. Extend with
   keyword-only arguments carrying defaults, and report the extension.
3. **Integers only** for money, prices, probabilities, scores and time. Section 1 is the whole unit system.
   A float is legal in exactly five places, none of which is ever journaled or hashed: a provider-reported
   USD cost; the USD and timeout fields of `GatewayConfig` and `BudgetTracker` (section 11.1); the statistics
   module's internal arithmetic (rounded to an integer before it is reported); the pinned fixed-order
   floating point inside `pmx.rng` (section 6), which is versioned; and the learned-policy boundary of
   section 16.5 (ruling R120): `pmx.features.view.float_view` inside `learn/` and `adversary/train/`, and
   the float that crosses into `pmx.features.quantise` at the inference boundary of
   `pmx.agents.families.torch_policy`, where it dies as a ppm integer. Nowhere else, and never in a document
   formula: this contract writes `PPM_ONE`, never a float scale literal.
4. **No wall clock, no `random.random`, no `uuid4`, no `set` iteration** in engine code. Every draw comes
   from a named substream of `pmx.rng`. `tests/test_architecture.py` scans for the first three.
5. **The engine never calls an LLM.** Only `pmx.gateway` is asynchronous; async functions carry the `a`
   prefix (`acollect_replies`, `acall_agent`, `apropose_patch`), never an `_async` suffix.
6. **English only**, in code, comments, docstrings, documents and identifiers. **Never the em-dash
   character** (U+2014) anywhere in produced content; `tests/test_architecture.py` sweeps the repository.
7. **No test passes by being weakened.** No relaxed assertion, no `skip`, no `xfail`, no loosened
   tolerance. The single legal skip is a live network test behind `PMX_LIVE=1`.

---

## 0. Table of contents

1. Units, conversions and rounding
2. Identifier formats
3. Canonical ordering
4. Canonical serialisation and hashes
5. Time, the bar grid, as-of and the safety lag
6. The RNG tree and the registered substreams
7. The data layer: schemas, window, filters, hardness, split, seal, data leak rules
8. The engine: bar phases, Observation, Actions, execution, fees, accounting
9. Journal v2: event catalogue, artefacts on disk, replay
10. Agents: the Agent, Genome, Memory and Hive protocols, the families
11. The gateway and the LLM agents
12. Scoring, statistics, the selection objective, the beat-the-market bar, folds and claims
13. Module map and file ownership
14. Wave plan cross-reference
15. Rulings (the gates record decisions here)
16. v3 interfaces (amendment C1: liquidity, decision latency, clusters, opportunities, features, learning)
17. Instruments across kinds (amendment C1b: the six kinds, the integer price model, session calendars,
    cash events, schedules, horizon forecasts, per-kind claims)
18. Discovery (amendment C1c: the sensor catalogue and gene, the hypothesis layer, minute grids,
    workflow genomes, the cohort; the two reviews of 2026-09-08 and 2026-09-09 landed in place)

---

## 1. Units, conversions and rounding

### 1.1 The unit table

| Concept | Type | Unit | Suffix | Range | Example |
|---|---|---|---|---|---|
| Money (cash, PnL, fees, notional) | `int` | cents of the market's currency | `_cents` | cash `>= 0`, deltas signed | `100_000` is 1 000 USD (or M1 000 on Manifold) |
| Price of one YES contract | `int` | basis points of one currency unit | `_bp` | `1..9_999` while trading; `0` or `10_000` at settlement | `6_327` is 63.27 cents |
| Probability | `int` | parts per million | `_ppm` | `0..1_000_000` | `632_700` is 63.27 percent |
| Brier | `int` | micro-units | `_micro` | `0..1_000_000` | `250_000` is 0.25 |
| Log score | `int` | micro-nats | `_micronats` | `10_050..4_605_170` | `693_147` is ln 2 |
| Skill (market Brier minus agent Brier) | `int` | micro-units, signed | `_micro` | `-1_000_000..1_000_000` | `12_500` is 0.0125 of Brier |
| Contract quantity | `int` | contracts | `size`, `position` | `size >= 1`, `position` signed | `-40` is 40 NO contracts held |
| Volume | `int` | thousandths of a contract (or of a mana) | `_milli` | `>= 0` | `12_500` is 12.5 contracts |
| Ratio, rate, fraction of a config | `int` | permille | `_permille` | `0..1_000` | `volume_cap_permille = 100` |
| Ratio that can be negative (return, drawdown, PMV, Sharpe) | `int` | basis points or milli-units, signed | `_bp`, `_milli` | signed | `max_drawdown_bp = -1_850` |
| Time | `int` | UTC epoch milliseconds | `_ms` | `>= 0` | `1_788_739_200_000` is 2026-09-07T00:00:00Z |
| Duration in bars | `int` | bars | `_bars` | `>= 0` | `ttl_bars = 3` |
| Interval | `int` | minutes | `interval_min` | `60` or `1_440` | |
| Gene | `int` | declared per gene | none | declared `[lo, hi]` | `shrink_permille = 880` |
| Descriptor | `int` | ppm or bp | `_ppm`, `_bp` | declared | `abstention_ppm = 120_000` |
| Price of any instrument (amendment C1b) | `int` | ticks of the instrument's `tick_size_micro` | `_ticks` (`_bp` on a binary, where one tick is one bp) | `1..PRICE_TICKS_MAX` | `6_341_257` is 63 412.57 USDT on BTCUSDT |
| Quantity of a continuous instrument (amendment C1b) | `int` | thousandths of one unit of position | `_milli` | `size_milli >= 1`, `position_milli` signed | `2_000` is two ES contracts, `1` is one milli-coin |
| Price scale (amendment C1b) | `int` | millionths of one quote unit | `tick_size_micro`, `point_value_micro` | `1..TICK_SIZE_MICRO_MAX`, `1..POINT_VALUE_MICRO_MAX` | a binary is `100` and `1_000_000` |

A YES contract pays exactly `10_000` bp (`100` cents) on YES and `0` on NO. A NO contract pays the mirror.
There is no other payout **on a binary**.

**Amendment C1b makes this table the `binary` row of a table over six instrument kinds** (section 17.1,
rulings R144 to R148). Every instrument declares `tick_size_micro` and `point_value_micro`, stores its
prices as `price_ticks` and its quantities as `size_milli`, and the cash of a fill is one exact product
divided once. A binary is `tick_size_micro = BINARY_TICK_SIZE_MICRO = 100` and `point_value_micro =
BINARY_POINT_VALUE_MICRO = 1_000_000`, so `price_ticks == price_bp` and no bp price already written
changes value; the rows above are read with that identity. A continuous instrument (`spot_crypto`,
`perp`, `fx`, `equity`, `future`) has no payout: it is marked, carried and forced flat (section 17.3).

### 1.2 Conversion formulas (all integer, all in `pmx.types`)

```python
PPM_ONE = 1_000_000
BP_ONE = 10_000
PRICE_MIN_BP = 1
PRICE_MAX_BP = 9_999
SETTLE_YES_BP = 10_000
SETTLE_NO_BP = 0
CENTS_PER_UNIT = 100
LOG_CLAMP_LO_PPM = 10_000      # 1 percent
LOG_CLAMP_HI_PPM = 990_000     # 99 percent

def ppm_from_bp(price_bp: int) -> int:        return price_bp * 100
def bp_from_ppm(prob_ppm: int) -> int:        return clamp_price_bp(prob_ppm // 100)
def clamp_price_bp(bp: int) -> int:           return max(PRICE_MIN_BP, min(PRICE_MAX_BP, bp))
def clamp_ppm(ppm: int) -> int:               return max(0, min(PPM_ONE, ppm))
def bp_from_v1_cents(cents: int) -> int:      return cents * 100          # v1 migration only
def brier_micro(prob_ppm: int, outcome: int) -> int:
    d = prob_ppm - outcome * PPM_ONE
    return (d * d) // PPM_ONE
def cost_cents(size: int, price_bp: int) -> int:                          # what a buyer pays
    return -((-size * price_bp) // CENTS_PER_UNIT)                        # ceil(size * price_bp / 100)
def proceeds_cents(size: int, price_bp: int) -> int:                      # what a seller receives
    return (size * price_bp) // CENTS_PER_UNIT                            # floor
def round_half_up(numerator: int, denominator: int) -> int:               # denominator > 0
    return (2 * numerator + denominator) // (2 * denominator)
def round_half_up_decimal(value: Decimal) -> int:                         # provider decimal strings only
    return int(value.to_integral_value(rounding=ROUND_HALF_UP))           # never a float, section 7.2
def bp_ratio(numerator: int, denominator: int) -> int:                    # signed, half away from zero
    scaled = numerator * BP_ONE
    q, r = divmod(abs(scaled), denominator)
    q += 1 if 2 * r >= denominator else 0
    return q if scaled >= 0 else -q
def milli_ratio(numerator: int, denominator: int) -> int:                 # same, in milli-units
    ...  # identical with 1_000 in place of BP_ONE
```

`brier_micro` truncates by at most one micro-unit; the numerator fits in 64 bits with room. `cost_cents`
rounds **against the agent** (up), `proceeds_cents` rounds **against the agent** (down): the engine never
creates a cent by rounding, and the accounting invariant of section 8.9 is exact because every journaled
cash delta is the integer the engine actually applied.

`round()` (banker's rounding) is banned everywhere; `//` on a signed value that is a ratio is banned
(it rounds toward minus infinity and overstates every loss). Use `round_half_up` for non-negative
quantities and `bp_ratio` / `milli_ratio` for signed ones.

The generalised conversions of section 17.1 (`notional_micro`, `cash_out_cents`, `cash_in_cents`,
`mark_value_cents`) obey the same rule and no other (ruling R146): one rounding, at the end, against the
agent for a cash movement, `round_half_up` for a score or a quantile. `cost_cents` and `proceeds_cents`
are their binary specialisation, `cost_cents(size, p) == cash_out_cents(size * MILLI, p, 100,
1_000_000)` for every legal `size` and `p`, and E2 asserts the identity.

**No integer formula in this document uses `/` or a float scale literal.** `PPM_ONE` and `BP_ONE` are the
only scale constants, division is `//` or one of the four helpers above, and a float scale literal in any
earlier draft means `PPM_ONE`. The two exceptions are explanatory and both stay inside section 1: the
`ceil(...)` and `floor(...)` comments beside `cost_cents` and `proceeds_cents`, which describe what the
integer expression does, and `Decimal` division inside `neg_ln_micronats` (section 1.3), which is exact
and returns an integer. **Every ratio in this document is `0` when its denominator is `0`**, and a bin,
bucket or slice with `n == 0` reports `n: 0` with every other field `0`; `round_half_up`, `bp_ratio` and
`milli_ratio` are never called with a zero denominator, the caller returns `0` first.

### 1.3 The natural logarithm, integer-safe

The log score needs `ln`. `math.log` reaches the platform libm and is not bit identical across glibc,
msvcrt and macOS, so it never touches a score. The one implementation is:

```python
from decimal import ROUND_HALF_UP, Decimal, localcontext

def neg_ln_micronats(prob_ppm: int) -> int:
    """-ln(p) in micro-nats for the probability `prob_ppm` parts per million, already clamped to
    [1 percent, 99 percent]."""
    with localcontext() as ctx:
        ctx.prec = 40
        value = -(Decimal(prob_ppm) / Decimal(PPM_ONE)).ln() * Decimal(PPM_ONE)
        return int(value.to_integral_value(rounding=ROUND_HALF_UP))
```

`Decimal.ln` is correctly rounded by the decimal specification, so the result is the same on every
platform. Worked values (tests pin them): `neg_ln_micronats(500_000) == 693_147`,
`neg_ln_micronats(10_000) == 4_605_170`, `neg_ln_micronats(990_000) == 10_050`.

### 1.4 Worked examples

- A Kalshi print at 63 cents is `price_bp = 6_300`; the market's implied probability is `630_000` ppm. An
  agent stating `700_000` ppm on a market that resolves YES scores `brier_micro(700_000, 1) = 90_000`
  (0.09); the market at `630_000` scores `136_900`; the agent's skill on that bar is `+46_900` micro.
- Buying 40 YES at `6_327` bp costs `cost_cents(40, 6_327) = ceil(253_080 / 100) = 2_531` cents (25.31
  USD). Selling them back at the same price returns `proceeds_cents(40, 6_327) = 2_530`. The cent lost is
  rounding, booked in the two `filled` events, never invented.
- Holding 40 NO contracts is `position = -40`. Opening it at a YES price of `6_327` costs
  `cost_cents(40, 10_000 - 6_327) = ceil(146_920 / 100) = 1_470` cents. On NO it pays
  `40 * 100 = 4_000` cents.
- A Manifold market priced at 0.4187 is `4_187` bp. `bp_from_ppm(418_700) == 4_187`; `bp_from_ppm(0)`
  is clamped to `1` and `bp_from_ppm(1_000_000)` to `9_999`, because a tradable price is never 0 or 1.
- v1's `price: 63` cents becomes `6_300` bp (`bp_from_v1_cents`), so every migrated bar close equals the
  v1 cent price times 100 to the unit. The life-average Brier deliberately **differs** from v1's: v1
  averaged 6 to 12 control points, the migration carries those points forward over 145 daily bars, and E3
  pins that difference (PRD 4.5, "on the migrated v1 paths it removes the control-point bias").
- `bp_ratio(-1_850, 100_000) == -185` and `bp_ratio(1_850, 100_000) == 185`: a loss and the mirror gain
  report the same magnitude.
- A Sharpe-like ratio of `mean_bp = 12`, `sd_bp = 85` daily equity changes is `milli_ratio(12, 85) == 141`
  milli-units.

---

## 2. Identifier formats

No identifier is ever derived from a clock, a UUID or a memory address. Every regex below is a constant in
`pmx.types` (`RE_MARKET_ID`, `RE_AGENT_ID`, ...) and the loader, the runner and the API validate against
them. All ids are ASCII and are legal Windows file names (no `:`, `<`, `>`, `"`, `/`, `\`, `|`, `?`, `*`).

| Entity | Format | Regex | Assigned by |
|---|---|---|---|
| Market | `<provider>-<slug>` | `^(kalshi\|manifold\|polymarket\|metaculus\|demo)-[A-Za-z0-9._-]{1,96}$` | importer (`slug` is the provider's own id or ticker, dots and dashes kept); `demo-<v1 id>` for the migrated pack |
| Provider | one of five | `^(kalshi\|manifold\|polymarket\|metaculus\|demo)$` | contract |
| Category | lowercase slug | `^(politics\|economics\|finance\|crypto\|sports\|science\|tech\|entertainment\|weather\|health\|world\|other)$` | importer, from a per-provider mapping table with `other` as the fallback. The order of the regex **is** the order of `pmx.types.CATEGORIES`, a 12-tuple, and `specialist.category`, `newsbayes.lexicon_id` and `src/pmx/lexicons/<category>.v1.json` all index it (`LEXICON_COUNT = len(CATEGORIES) = 12`) |
| Agent | lowercase name | `^[a-z][a-z0-9_]{0,31}(-[0-9a-f]{8})?$` | the roster (hand-written names such as `market_follower`) or the optimizer (`p<idx:03d>-<genome_hash[:8]>`, e.g. `p017-3fa9c2e1`) |
| Family | lowercase name | `^[a-z][a-z0-9_]{0,23}$` | contract, section 10.5 |
| Genome hash | 64 lowercase hex | `^[0-9a-f]{64}$` | `sha256(canonical_json(genome_dict))`, section 4 |
| Dataset name | lowercase slug | `^[a-z][a-z0-9_-]{0,31}$` | the builder's caller (`--out data/datasets/<name>`) |
| Dataset hash | 64 lowercase hex | `^[0-9a-f]{64}$` | `pmx data seal`, section 7.8 |
| Run (backtest) | `r-<dataset_hash[:8]>-<seed>-<config_hash[:8]>` | `^r-[0-9a-f]{8}-[0-9]{1,19}-[0-9a-f]{8}$` | `run_backtest`; deterministic, so the same inputs land in the same directory |
| Run (evolution) | `e-<dataset_hash[:8]>-<seed>-<config_hash[:8]>` | `^e-[0-9a-f]{8}-[0-9]{1,19}-[0-9a-f]{8}$` | `pmx evolve` |
| Claim | `c-<dataset_hash[:8]>-<provider>-<genome_hash[:16]>` | `^c-[0-9a-f]{8}-(kalshi\|manifold\|polymarket\|metaculus\|demo)-[0-9a-f]{16}$` | `pmx claim`; one per `(dataset_hash, provider, genome_hash)`, which is what makes reuse detectable by file name while leaving each provider its own claim (section 12.6 pools nothing across providers) |
| News item | `<source_code>-<yyyymmdd>-<idx:04d>` | `^(wce\|wasof\|wb\|gd\|mfc)-[0-9]{8}-[0-9]{4}$` | the news fetcher, positional inside the day the id names, per source. For `wce` that day is the **page day** `D`, not `day_start_ms(published_at_ms)` (which is `D + 1`, section 5.5); for every other source the two agree |
| Order | `o-<seq:08d>` | `^o-[0-9]{8}$` | execution, one counter per run from `00000001`, assigned in the canonical order of section 3 |
| Hive entry | `h-<seq:08d>` | `^h-[0-9]{8}$` | the hive, one counter per run from `00000001` |
| Lexicon | `<category>.v<n>` | `^[a-z]+\.v[0-9]+$` | D5, shipped as `src/pmx/lexicons/<category>.v<n>.json` |
| Fee schedule | `<provider>-<name>-<yyyy-mm>`, or the literal `demo-zero` | `^([a-z]+-[a-z0-9]+-[0-9]{4}-[0-9]{2}\|demo-zero)$` | E2, section 8.8 |
| Live forecast | `lf-<yyyymmdd>-<agent_id>-<market_id>` | `^lf-[0-9]{8}-[a-z][a-z0-9_]{0,31}(-[0-9a-f]{8})?-(kalshi\|manifold\|polymarket\|metaculus\|demo)-[A-Za-z0-9._-]{1,96}$` | L1 |
| Event | `seq: int` | `>= 1`, dense | the journal, section 9 |

Source codes: `wce` Wikipedia Current events, `wasof` Wikipedia article as of a date, `wb` Wayback front
page, `gd` GDELT, `mfc` Manifold comment.

`config_hash` is `sha256(canonical_json(config_dict))` where `config_dict` is the `RunConfig` of section
8.1 rendered by `RunConfig.to_dict()`. Because `RunConfig` carries `market_ids_hash` and `fold` (section
8.1), a run id is unique per `(dataset, seed, config, market set, fold)`: the training and the validation
run of one generation have **different** run ids and therefore different directories, and O1's test asserts
`run_id(train) != run_id(validation)` for one generation. Two runs whose configs differ only in `amnesic`
or `no_hive` also have different run ids, but that alone is never evidence that learning did anything: the
behavioural form of AC-5 is in section 9.2.

---

## 3. Canonical ordering

Whenever a collection is iterated in a way that can reach an event, a fill, a score or a file, it is in one
of these orders and no other. Iterating a `set`, a `dict` built from a `set`, or relying on `dict`
insertion order for output is forbidden in engine code; a `set` is for membership tests only. Helpers live
in `pmx.types` (`sorted_market_ids`, `sorted_agent_ids`) and are the only spelling.

| Collection | Order | Helper |
|---|---|---|
| Markets of a dataset or a run (every kind) | `(resolved_at_ms, id)` ascending, where a continuous instrument's `resolved_at_ms` is its `MarketMeta` value of 7.2 (`delisted_at_ms`, else the dataset's window end; amendment C1b, ruling R186) | `sort_markets(markets)`, `sort_market_metas(metas)` |
| Markets inside an observation, an action set, a settlement loop | `id` ascending by code point | `sorted_market_ids` |
| Agents (roster, replies, settlement, equity marking, culling) | `agent_id` ascending by code point | `sorted_agent_ids` |
| Bars of a market | `t_ms` ascending, dense on the grid | by construction (the loader refuses a gap) |
| Trades of a market | `(t_ms, price_bp, size_milli, side)` ascending | the importer sorts; the loader refuses disorder |
| Cash events of one instrument applied at one bar | `(kind order in CASH_EVENT_KINDS, t_ms, cash_event_id)` ascending (amendment C1b, ruling R193); an instrument file stores its events chronologically by `(t_ms, kind order, cash_event_id)` and execution regroups them per application bar | execution; the loader refuses disorder in the file |
| News items in a digest | `(-match_score_permille, published_at_ms, news_id)`: best link first, then oldest, then id | `rank_news` |
| News items in a dataset file | `(published_at_ms, news_id)` ascending | the builder |
| Hive entries in a view | `(visible_from_ms, entry_id)` ascending; lessons additionally ranked by section 10.4 | the hive |
| Order intents of one agent in one bar | exactly the order submitted, after per-market validation | the runner |
| Orders across agents in the execute phase | `agent_id` ascending, then submission order | the runner |
| Resting limit orders of one market at a fill | `(order_id)` ascending (time priority, since order ids are dense in submission order) | execution |
| Events | `seq` ascending | the journal |
| Population in `generation_closed` | objective descending (section 12.6), then `agent_id` | the optimizer |
| Files in a dataset hash | relative POSIX path ascending by code point | `pmx data seal` |
| Keys of every JSON object written | code point ascending | `canonical_json` |

Ties are broken by the last key in the tuple, and every tuple ends in an id, so no ordering is ever
ambiguous.

---

## 4. Canonical serialisation and hashes

### 4.1 `canonical_json`

```python
def canonical_json(payload: object) -> str:
    """json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    over a structure holding only dict, list, tuple (rendered as list), str, int, bool and None.
    Raises NonCanonicalValueError on a float, a set, bytes, an Enum that is not a str subclass, or any
    other type. Object keys must be str. The result carries no newline."""
```

Owned by D7 (`pmx.journal`), used by everyone: journal lines, dataset files, manifests, genome and config
hashes, claims, live forecasts. There is no second encoder. `stable_json` of Exchange (the float-tolerant
sibling) **does not exist in pmx**: observations carry no float, so the one encoder suffices, and an
observation hash may legally be journaled (section 9.3).

**JSON Schema does not enforce the float ban.** A draft 2020-12 validator accepts `3200.0` for an `"integer"`
(zero-fraction floats are integers to the specification). The ban is enforced twice, and the schemas are the
third, weaker line: `canonical_json` raises on any Python `float` at every write, and D1's pydantic models
declare integer fields in strict mode (`StrictInt`), so `3200.0` read from a file is refused at load time.
`tests/test_contract_schemas.py` pins the schema half with a fractional float and documents the other half.

### 4.2 File conventions

Every text artefact is UTF-8 without a BOM, LF line endings, and is written through one of two spellings:

```python
JOURNAL_ENCODING = "utf-8"
JOURNAL_NEWLINE = "\n"
open(path, mode, encoding=JOURNAL_ENCODING, newline=JOURNAL_NEWLINE)     # mode "w" or "a"
```

Reading also passes `newline=JOURNAL_NEWLINE`, and a line containing `\r` is **rejected**
(`NonCanonicalValueError`), never normalised: the development platform is Windows, where the default text
mode rewrites `\n` to `\r\n` and would leave the in-memory hash right and the bytes wrong.

- A JSONL file (`journal.jsonl`, `news/<day>.jsonl`, `live/forecasts.jsonl`, `llm_trace.jsonl`) is
  `canonical_json(obj) + "\n"` per line, nothing else. `llm_trace.jsonl` is the one file that may carry
  floats (provider USD); it is written with `json.dumps(sort_keys=True, separators=(",", ":"))` directly and
  is outside every hash.
- A JSON file (`markets/<id>.json`, `manifest.json`, `results.json`, `claims/<id>.json`) is
  `canonical_json(obj) + "\n"`: one line. Human readers use `pmx ... --pretty` or the UI; the bytes on disk
  are canonical so hashes are stable.

### 4.3 Hashes

| Hash | Algorithm | Over | Written to |
|---|---|---|---|
| `journal_hash` | SHA-256, hex | the exact bytes of `journal.jsonl` (equivalently the concatenation of every line) | `runs/<run_id>/journal.sha256` as `<hex>  journal.jsonl\n`; `manifest.json.journal_hash` |
| `dataset_hash` | SHA-256, hex | `"\n".join(f"{relpath} {sha256_hex(file_bytes)}" for every file under markets/, news/, wiki_asof/, clusters/ sorted by relpath) + "\n"` | `manifest.json.dataset_hash` |
| `genome_hash` | SHA-256, hex | `canonical_json(genome.to_dict())` | run manifests, claims, `generation_closed` |
| `config_hash` | SHA-256, hex | `canonical_json(config.to_dict())` | run ids, run manifests |
| `obs_sha256` | SHA-256, hex | `canonical_json(observation.to_dict())` | `observation_built` |
| `forecast_hash` (live) | SHA-256, hex | `canonical_json({"agent_id", "market_id", "prob_ppm", "forecast_at_ms", "genome_hash"})` | `live/forecasts.jsonl` |
| `derive_seed` (RNG) | BLAKE2b-256 | `uint64_be(root_seed) || 0x1f || utf8(qualified_name)` | never written; section 6 |

The journal digest is SHA-256 (the PRD names the file `journal.sha256`); the seed derivation stays
BLAKE2b because it is ported verbatim from Exchange and changing it would change every draw for no gain.
`manifest.json` is excluded from `dataset_hash` because it carries the hash; the manifest's own integrity is
the `sealed: true` flag plus the recomputation that `pmx data verify` performs. `clusters/` is inside the
walk (amendment C1, ruling R117), and the same exclusion argument decides what may be written inside it:
`clusters/clusters.json` and `clusters/overrides.json` carry **no `dataset_hash` field of their own**,
because a file whose bytes are an input to the hash cannot also hold it (ruling R128). What pins the
hand-written review is `clusters.json.overrides_sha256`, which the walk covers, and the manifest's
`clusters` block of section 16.3. A dataset with no `clusters/` directory hashes exactly as it did before
the amendment, because the walk of an absent directory adds no line.

### 4.4 What is forbidden in a journal

Anything that varies between two runs of the same seed on the same dataset:

- wall-clock timestamps, durations, latencies;
- provider costs, token counts, retry counts, model text of a failed call, the rationale text of an LLM
  reply (it goes to `llm_trace.jsonl`);
- floats (structurally rejected by `canonical_json`), memory addresses, `repr` of objects;
- the iteration order of a `set` or a `dict` built from one.

A journal event may carry the **outcome** of an LLM call (its validated actions, its forecasts, its
lessons) because the run replays from the journal without the provider: what the model said is data, what
it cost is not.

---

## 5. Time, the bar grid, as-of and the safety lag

### 5.1 Time is an integer

Every instant is an `int` of UTC epoch milliseconds, suffix `_ms`. ISO-8601 strings appear only as a
convenience beside the integer in manifests (`freeze_date: "2026-09-07"` next to `freeze_ms`) and in the
UI. The engine never parses a date string; the loader does, once, and refuses a string without a `Z` or an
explicit offset.

```python
MS_PER_MINUTE = 60_000
MS_PER_HOUR = 3_600_000
MS_PER_DAY = 86_400_000
INTERVALS_MIN = (1, 60, 1_440)          # the minute grid is amendment C1c's (section 18.3, ruling R241)
def interval_ms(interval_min: int) -> int: return interval_min * MS_PER_MINUTE
def bar_of(t_ms: int, interval_min: int) -> int: return (t_ms // interval_ms(interval_min)) * interval_ms(interval_min)
def day_start_ms(t_ms: int) -> int: return (t_ms // MS_PER_DAY) * MS_PER_DAY
```

### 5.2 The bar grid

A bar is identified by its **open** time `t_ms`, a multiple of `interval_ms`. Daily bars open at 00:00:00Z.
The bar covers `[t_ms, t_ms + interval_ms)`. A market's bars are dense from `bar_of(created_at_ms)` to
`bar_of(resolved_at_ms)` inclusive; the loader refuses a gap or a duplicate. A bar with no trade repeats
the previous close as `open = high = low = close = vwap` with `volume_milli = 0`, `n_trades = 0`.

A continuous instrument's bars are dense **on its session calendar** (amendment C1b, section 17.2,
ruling R149): a bar exists iff its interval intersects a session of the sealed calendar the instrument
names, a bar outside every session is a load error, and a missing bar at a grid point inside a session is
the gap the sentence above already refuses. The `continuous` calendar every binary carries has one
session covering the window, so for a binary the rule is exactly the sentence above.

Resampling (D6, `pmx.data.resample.bars_from_trades`): `open` is the first print in the bar, `close` the
last, `high`/`low` the extremes, `vwap = round_half_up(sum(price_bp * size_milli), sum(size_milli))`,
`volume_milli = sum(size_milli)`, `n_trades` the count. A bar before the first trade takes
`first_price_bp` (the provider's opening quote when known, else the first print) as its carried close.

**Three grids, one per dataset** (amendment C1c, section 18.3, rulings R241 and R251). `INTERVALS_MIN` is
`(1, 60, 1_440)`: daily, hourly and **minute**. The rules above hold on every grid unchanged (a minute
bar opens at a multiple of `MS_PER_MINUTE`), one grid per run and one dataset per grid hold (5.3, 7.8),
and a minute dataset is built per instrument or series on demand for the event studies and the minute
agents, never for the evolution of a whole population. **The hourly grid is the headline Kalshi grid**
(decision D-R5): Kalshi's median life is 29 days and it publishes 1-minute candlesticks, so a daily grid
discards its intraday content and the latency rule of 16.2 costs a full day; `y2026h` is the headline
Kalshi dataset, the daily grid stays for Manifold and for the showcase pack (5.6), and which news sources
a minute dataset may carry is 18.3's rule.

### 5.3 The run calendar

A run has `t0_ms`, `t1_ms` and `interval_min`. It processes every bar `t` with `t0_ms <= t < t1_ms`
in ascending order, one bar phase cycle each (section 8.2). At bar `t`, for a market `m`:

| Predicate | Definition |
|---|---|
| `listed(m, t)` | `bar_of(created_at_ms) <= t <= bar_of(resolved_at_ms)` |
| `tradable(m, t)` | `listed(m, t) and t + interval_ms <= close_at_ms and not settles(m, t)` |
| `settles(m, t)` | `bar_of(resolved_at_ms) == t` |
| `open(m, t)` (appears in observations) | `listed(m, t) and not settled before t` (that is `t <= bar_of(resolved_at_ms)`) |
| `actionable(m, t)` (amendment C1, section 16.2) | `tradable(m, t + interval_ms)`: an action decided at `t` executes at the open of `t + interval_ms`, so this is the predicate a **decision** is worth taking under, while `tradable` stays the predicate a **fill** may land under |

Only a bar that lies **entirely inside the trading window** is tradable, and the settling bar never is.
The reason is a leak with money attached: on a daily grid the bar containing `close_at_ms` (and, when
`close_at_ms` and `resolved_at_ms` share a bar, the settling bar) carries prints made after the close and
after the outcome was known (the election-night tape at `9_900` bp), and section 8.6 would fill a market
order against that bar's own price. E2's tests assert no `filled` event exists at `bar_of(m.close_at_ms)` or at
`bar_of(m.resolved_at_ms)`.

Between the last tradable bar and `resolved_at_ms` a market is open but not tradable: positions are held,
orders are refused with `not_tradable` (section 8.6 step 0), forecasts are still recorded and scored. A
market settles in the bar containing `resolved_at_ms`, after the execute phase of that bar.

**Amendment C1 adds one bar of decision latency** (section 16.2, ruling R107) and with it the fourth
predicate above. Ruling R9 stands untouched: no fill exists at `bar_of(close_at_ms)` or at
`bar_of(resolved_at_ms)`, and only a bar entirely inside the trading window can fill. What C1 moves is
which decision feeds a fill, never where a fill may land. The consequence is stated rather than softened:
a market's last **actionable** bar is one bar before its last **tradable** bar, an action decided on the
last tradable bar has nowhere to fill, and it is journaled `order_rejected(not_tradable)` at the execute
phase of the next bar (section 8.6 step 0, section 16.2).

**One grid per run.** `config.interval_min` must equal `manifest.interval_min` and the `interval_min` of
every market of the run; `run_backtest` raises `InvalidConfigError` otherwise. There is no run-time
resampling, so `m.bar_at(t)` is always defined for a listed market. An hourly claim (PRD open question 2)
needs a second dataset built at `interval_min = 60`, not a second reading of the same one.

**The run calendar is the union of the instruments' bar timestamps** (amendment C1b, section 17.2,
ruling R149). A bar `t` of the run is a grid point in `[t0_ms, t1_ms)` at which at least one instrument
of the run has a bar; on a run that carries a binary that is every grid point, as above, and on a run of
session instruments alone a weekend is not a bar and produces no event. For a continuous instrument
`i` the table above reads: `listed(i, t)` is `bar_of(listed_at_ms) <= t` and before `bar_of(delisted_at_ms)`
when it is set; `open(i, t)` is `listed(i, t) and in_session(i, t)`; `tradable(i, t)` is `open(i, t) and
t < last_bar(i)`, where `last_bar(i)` is the last bar of the run at which the instrument is open;
`settles(i, t)` never holds and `closes(i, t) = (t == last_bar(i))` is the bar of the forced flat of
section 17.3 (ruling R150); `actionable(i, t)` reads `t + interval_ms` as the instrument's **next bar**,
which after a Friday session is Monday's first bar. Ruling R9 stands for every kind: a fill lands only on a
bar the instrument is tradable at, and never on `last_bar(i)`, whose only fill is the engine's forced
flat. In an observation `MarketView.tradable` on a continuous instrument carries `open(i, t)` and not
`tradable(i, t)`, because `t < last_bar(i)` would announce the instrument's last bar one bar ahead
(ruling R181); the engine still refuses every agent fill at `last_bar(i)`. `BarSlice.closing_ids` carries the
instruments with `closes(i, t)` and `Calendar.last_bar`, `next_bar` and `prev_bar` (8.3) are the one
implementation of the three lookups this table needs (ruling R187).

### 5.4 As-of: what an agent may know at bar `t`

`now_ms = t` (the bar's open). The observation builder (E1) is the one place these rules are applied, and
it applies them by filtering, never by trusting the agent:

| Data | Visible at `now_ms` iff |
|---|---|
| a bar `b` of a market | `b.t_ms + interval_ms <= now_ms` (completed bars only) |
| the "current price" | the close of the last completed bar, carried in `MarketView.last_price_bp`. **When no bar is completed at `now_ms`** (the first bar of a market's life) `last_price_bp = market.first_price_bp`, `bars = ()` and `best_bid_bp = best_ask_bp = None`; the market's own baseline forecast on that bar is the same value (section 12.1) |
| a trade | `trade.t_ms < now_ms` |
| a quote (`yes_bid_bp`, `yes_ask_bp`) | from the last completed bar only |
| a news item | `item.visible_from_ms <= now_ms` |
| a hive entry | `entry.visible_from_ms <= now_ms`. A `forecast` or `resolution` entry of market `m` is stamped `bar_of(resolved_at_ms) + interval_ms`, so it is released at the **first bar strictly after** the settling bar and no agent ever reads another agent's forecast on a market that is still open (section 10.4) |
| a research result | granted at the previous bar (section 8.6), so its content is as of `now_ms - interval_ms` and is filtered by the same rules |
| memory | the agent's own memory, filtered to records with `written_at_ms <= now_ms`; every record carries that stamp (section 10.3), including a memory snapshot loaded from an earlier run |
| `close_at_ms` | always on a binary (public on every venue); `0` in the `MarketView` of a continuous instrument, whose `delisted_at_ms` is future information (amendment C1b, ruling R181) |
| an applied `CashEvent` of a continuous instrument | its application bar has completed: `applies_at(e) + interval_ms <= now_ms` (section 17.3); carried in `MarketView.cash_events` (amendment C1b, ruling R183). An event whose application bar has not completed is never visible, however far in the past the venue announced it |

The agent decides at bar `t` on completed information and its market orders fill at the **open of bar
`t + interval_ms`**, which it has not seen and cannot see until that bar has completed (amendment C1,
section 16.2, ruling R107; the earlier spelling, "fill against bar `t`'s own vwap", is superseded). That
is the honest shape of "trade at the next price".

### 5.5 The safety lag

`safety_lag_ms` is a dataset parameter (default `SAFETY_LAG_MS_DEFAULT = 21_600_000`, six hours),
stamped in the manifest and applied **at build time** by D5 as `visible_from_ms = published_at_ms +
safety_lag_ms`. The observation builder reads `visible_from_ms` and nothing else, so the lag cannot be
skipped by a consumer.

For a Wikipedia Current events bullet, `published_at_ms` is **the timestamp of the first revision of
`Portal:Current events/<day>` that carries the bullet** (decision D-R3, ruling R249; the item's `revid`
names that revision and `published_at_source = "revision"`), so that a bullet added at 09:14Z is visible
from 15:14Z and not from the next morning; when the revision history is unavailable the stamp falls back to
the **end of day D**, `day_start_ms(D) + MS_PER_DAY` (00:00:00Z of `D + 1`, `published_at_source =
"page_day"`), which with the default lag is the PRD's "readable from D+1 06:00 UTC". The six-hour figure
was a guess about the page and is now a floor over a measured instant. A Manifold comment carries its own
`createdTime` as `published_at_ms`. A Wayback snapshot carries its capture time. An as-of Wikipedia
article carries the revision timestamp. A Hacker News story carries `created_at_i * 1_000` (18.3).

**The lag is per source** (amendment C1c, section 18.3, ruling R241): `visible_from_ms = published_at_ms
+ lag(source)`, where `lag(source)` is `manifest.news.safety_lag_by_source[source]` when the manifest
carries the block and `manifest.safety_lag_ms` otherwise, so a dataset built before the amendment
recomputes to the same bytes. The defaults are `SAFETY_LAG_MS_BY_SOURCE` of `pmx.types` (six hours for a
day-granular source, fifteen minutes for GDELT, five minutes for Hacker News, one minute for a Manifold
comment or a filing, none for a release whose time is the release), defaults the first minute build
reports against, never below the source's granularity.

### 5.6 The freeze

A dataset has `freeze_ms = day_start_ms(freeze_date)`. Its window is
`[freeze_ms - window_days * MS_PER_DAY, freeze_ms - MS_PER_DAY)` on `resolved_at_ms` (the freeze day
itself is excluded), with `BuildConfig.window_days = 365` by default. No file in the dataset may carry an
instant `> freeze_ms`: the builder refuses a news item with `published_at_ms > freeze_ms` and a market with
`resolved_at_ms >= freeze_ms` (`LeakError`).

**The window is explicit and bounded** (decision D-S3, ruling R262). `window_days` is a `BuildConfig`
field written into every manifest beside the true `resolution_span {min_ms, max_ms}` of the markets kept,
and `BuildConfig.__post_init__` refuses a value above `WINDOW_DAYS_MAX = 730` with `InvalidConfigError`,
for two reasons that no flag may override: a market that resolved before a model's knowledge cutoff is a
possible **recall** rather than a forecast, so an older resolution buys nothing an LLM row can be scored
on; and a regime three years old is not the regime being traded, so an older tape teaches a scripted
family the wrong market. A leaderboard row computed on a dataset with `window_days > 365` carries
`window_days:<n>` in its `labels` (12.10).

**Two purposes, one exemption** (decision D-S4, ruling R263). `DatasetManifest.purpose` is `"research"`
or `"showcase"`. A **showcase** dataset holds landmark events kept apart rather than thrown away (the 2016
referendum, a central-bank surprise, a crypto threshold: the events of the v1 demo pack and the pack DS2
builds, 7.1); it is **exempt** from the window rule of this section and from nothing else: it seals and
replays like any other dataset, `run_backtest` runs it, and it is never the source of a fold, a fitness
value, a rule promotion, an insight or a claim, which `make_folds`, `run_generation`, `evolve`, `claim`,
the rule tester and the feature matrix each refuse with `ShowcaseDatasetError` (13.1) before reading a
market. **The carry-forward of 8.1 is on that list too** (ruling R291): `run_backtest` raises
`ShowcaseDatasetError` when the run named by `config.memory_from_run_id` or `config.hive_from_run_id` ran
on a `purpose: "showcase"` dataset, and `LeakError` when that run's `dataset_hash` differs from this
run's. A showcase pack holds landmark events resolved years ago, so its `t1_ms` sits below any research
`t0_ms` and 8.1's instant guard passes by construction: without these two refusals a 2016 referendum
would flow into a research run's `calibrator` bin table and its hive resolutions, and 8.1 calls memory
carried between runs a channel into an observation. No flag lifts either refusal. A **research** dataset obeys the window. The field replaces the ad hoc `Dataset.is_demo_pack`
(an unsealed pack whose only provider is `demo`), which the loader reads as `showcase` on a manifest
written before this amendment and which is deleted from the code by DS1; the builder writes `purpose`
into every manifest from then on.

---

## 6. The RNG tree and the registered substreams

### 6.1 Port of `pxe.rng`

`pmx.rng` (D7) is `GAN/Exchange/src/pxe/rng.py` ported with these changes and no other: the import of
`pxe.errors.UnknownSubstreamError` becomes `pmx.errors.UnknownSubstreamError`; the registries of section
6.3 replace Exchange's; `RNG_ALGORITHM_VERSION` starts at `"1.0.0"` and is re-exported by `pmx.types` as
part of the engine version tuple. Everything else is verbatim: `derive_seed`, `RngTree` (`substream`,
`fresh_substream`, `child`, `seed_for`), the pinned `_log`, `_exp`, `_norm_ppf`, `_randbelow`, and the
draw helpers `shuffle_seeded`, `choice`, `choices_weighted`, `sample_without_replacement`, `random_unit`,
`random_open_unit`, `normal`, `lognormal`, `bernoulli`, `randint`, `uniform`, `beta`, `stable_key`,
`ordered`.

Only `getrandbits` of `random.Random` is ever consumed. `random.random`, `.shuffle`, `.choice`, `.gauss`
and friends are banned (their algorithms are implementation details and reach libm); the architecture test
scans for them.

### 6.2 Who builds the tree

```python
SEED_SPACE = 2**63          # seeds are persisted in sqlite BigInteger columns; the tree accepts 2**64

# a backtest run
tree = RngTree(config.seed)                                          # built by run_backtest's caller
agent_rng = tree.child(f"agent/{agent_id}").substream(f"agent.{agent_id}")   # handed to each scripted agent at reset
stats_tree = tree.child("stats")                                      # handed to pmx.metrics.stats

# an evolution run
evo = RngTree(seed).child("evolution")
gen_tree = evo.child(f"generation/{g}")                              # parents, mutation, crossover, immigrants, novelty of generation g
run_seed_g = derive_seed(seed, f"generation/{g}") % SEED_SPACE       # the seed of generation g's backtest
```

The runner never constructs an `RngTree` of its own; it receives one as the keyword-only `tree` argument
of `run_backtest` (the literal signature is in section 12.11), and `run_backtest`'s caller builds it as
`RngTree(config.seed)`. The plan's third spelling (`run_backtest(dataset, roster, config, seed)`) is
superseded. The runner consumes **no** randomness: every ordering in the engine is canonical (section 3),
so there is no `runner.*` substream and there must not be one.

### 6.3 Registered substreams

Exact names (`pmx.rng.SUBSTREAMS`):

```
stats.bootstrap            stats.permutation
evolution.parents          evolution.mutation        evolution.crossover
evolution.immigrants       evolution.novelty         evolution.prompt_mutation
dataset.subsample          contamination.paraphrases
test.scratch
```

Parametric families (`pmx.rng.SUBSTREAM_PREFIXES`, `prefix + "." + non-empty suffix`):

```
agent.<agent_id>           one scripted agent's own generator, built by the runner at reset
test.<anything>            test scaffolding only
```

Adding randomness means adding a name here **and** in `pmx.rng` in the same commit. An unregistered name
raises `UnknownSubstreamError`. `numpy` (allowed only in `pmx.metrics.stats`) is seeded as
`numpy.random.default_rng(tree.seed_for("stats.bootstrap") % 2**64)` and never from its global state.
`permutation_null` draws its shuffles from `stats.permutation` and its inner resamples from `stats.bootstrap`
(ruling R219).

### 6.4 Determinism claims

| Run kind | Guarantee | Enforced by |
|---|---|---|
| Scripted backtest | same `(dataset_hash, roster, config, seed)` gives a byte-identical `journal.jsonl` on any machine | `pmx replay`, `tests/test_runner.py`, gate G2 over 50 seeds |
| LLM backtest | the engine's decisions are a deterministic function of the replies it received; the recorded journal replays byte for byte | `tests/test_runner.py::test_replay_from_journal_only` with a scripted gateway |
| Evolution | same `(dataset_hash, config, seed)` gives identical generations; resuming from generation `g` gives an identical continuation | `tests/test_evolution.py` |
| Statistics | same `(journal, seed)` gives identical integer intervals | `tests/test_stats.py` |
| `torch_policy` backtest | the recorded journal **replays** byte for byte on any machine, with no GPU and no training library; it **reruns** byte-identically only when the genome's card declares `inference_kind == "integer_table"`, because a float32 forward pass is not bit-reproducible across BLAS builds | `tests/test_torch_policy.py` (R3e), section 16.5, ruling R120 |

---

## 7. The data layer

### 7.1 Directory layout

```
data/
  demo_v1/                          the 12 migrated v1 markets, source "reconstructed", never sealed (D1)
    manifest.json                   sealed: false, dataset_hash present for reproducibility
    markets/demo-<id>.json
  lexicons/<category>.v<n>.json     newsbayes word lists (D5)
  datasets/<name>/                  git-ignored, built by pmx data build (D6)
    manifest.json                   dataset.v1.json
    markets/<market_id>.json        market.v2.json
    news/<yyyymmdd>.jsonl           one line per NewsItem, news.v1.json, sorted (published_at_ms, news_id)
    wiki_asof/<market_id>/<yyyymmdd>.json   point-in-time background article snapshots, news.v1.json (kind "background")
    clusters/clusters.json          event clusters and constraints, cluster.v1.json (section 16.3, R1b)
    clusters/overrides.json         the hand-written review, cluster.v1.json#/$defs/override_file
    taxonomy/tags.v1.json           the tag vocabulary the build tagged with, copied from src/pmx/lexicons/ (7.14, DS2)
    taxonomy/kalshi_series_facets.v1.json   the sealed series-to-facets map the tagger read first (7.14, DS2)
    contamination.json              per-model contaminated market ids, outside the dataset hash (section 11.5)
    cache/                          raw provider responses, excluded from the hash, may be deleted
audits/<dataset_hash[:16]>/         TRACKED, outside every dataset directory and every hash (ruling R296)
    linker.json                     the 50-link precision audit of 7.6, keyed by dataset_hash (D-R4)
    taxonomy.json                   the 50-tagging audit of 7.14, keyed by dataset_hash (D-S9)
```

`taxonomy/` is inside the walk of 4.3 (a tag decides a cohort, a cohort decides a claim row, so the
vocabulary a build tagged with is part of what the hash pins, ruling R267). The two human audits are
outside it, like `contamination.json`, because an audit happens after the seal and is keyed by the hash it
audits; they live in the **tracked** `audits/` tree rather than under the git-ignored `data/datasets/`,
because fifty reviewer verdicts cannot be regenerated and are the sole evidence behind a label gate G3
reads (ruling R296).

**The day key of a news file** is `day_start_ms(item.published_at_ms)` rendered as `yyyymmdd`, which for a
Wikipedia Current events page of day `D` is `D + 1` (section 5.5), while the item's `news_id` names `D`
(section 2). The loader validates that every item in a file satisfies
`day_start_ms(item.published_at_ms) == the file's day` and refuses the file otherwise, so the two spellings
can never drift: `wce-20160623-0007` lives in `news/20160624.jsonl`.

**Background snapshots (D5).** For every market, D5 fetches one `wikipedia_asof` revision per 7 days of
market life through `prop=revisions&rvstart=<asof_day>T23:59:59Z&rvdir=older&rvlimit=1`, and **none** with
`asof_day` at or after `bar_of(resolved_at_ms)`. The item stores the `revid` and the `asof_day` it asked
for (section 7.3); the loader refuses an item whose `published_at_ms > day_start_ms(asof_day) + MS_PER_DAY`,
because that is the signature of the highest-value leak in the design (today's article on "will X win",
which states the outcome, stamped with an early date). D5's test asserts that the stored text of a resolved
market's snapshot is byte-identical to the revision named by its `revid`.

**A showcase dataset is exempt from the window rule** (decision D-S4, ruling R263; section 5.6).
`data/demo_v1/` holds markets that resolved between 2016 and 2024, so section 5.6's window check does not
apply to it: its `window.start_ms = day_start_ms(min created_at_ms)`, its `window.end_ms =
max(resolved_at_ms) + 1`, its `freeze_ms = day_start_ms` of the build's freeze date, and its month edges
are section 7.7's formula applied to that window. The loader skips the 5.6 window check for a dataset
whose `purpose` is `showcase` (read as such from a manifest that predates the field when `sealed: false`
and the only provider is `demo`, the old `is_demo_pack` signature), and for no other dataset; it never
skips the freeze check, and it never lets a showcase dataset reach a fold, a fitness value, a rule
promotion, an insight or a claim (`ShowcaseDatasetError`). The demo pack stays the migration identity of
7.10; the **showcase pack** DS2 builds (decision D-S5, ruling R264) is a second showcase dataset, sealed,
with a few dozen landmark markets carrying the same bars, trades, news and as-of stamps as a research
market wherever a real tape survives in the Wayback archive or in Manifold's history, and a `notes` entry
documenting what could not be sourced, because a showcase whose data is shallower than the research data
teaches the wrong lesson about the product.

### 7.2 Market (`market.v2.json`, `pmx.types.Market`)

| Field | Type | Rule |
|---|---|---|
| `schema_version` | `"market.v2"` | literal |
| `id` | market id | section 2 |
| `provider` | provider | section 2 |
| `provider_id` | `str`, 1..128 | the provider's own ticker or id, verbatim |
| `url` | `str` | `https://...`; `""` for `demo` |
| `question` | `str`, 1..500 | |
| `description` | `str`, 0..4000 | resolution criteria as published; truncated at import with `...` |
| `category` | category | section 2 |
| `tags` | `list[str]`, each `^[a-z0-9_-]{1,32}$`, `<= 16`, sorted, unique | the sorted union of the market's facet values and builder labels from the controlled vocabulary of 7.14 (amendment C1c, decision D-S6, ruling R265); the builder refuses a value outside `tags.v1.json`. Raw provider strings live in `provider_labels`, never here |
| `provider_labels` | `list[str]`, each `^[a-z0-9_-]{1,32}$`, `<= 16`, sorted, unique, **optional** | the provider's own labels verbatim (a Kalshi series ticker, a Manifold group slug, `nonpredictive`): never a cohort key, never displayed as a tag, kept for the reviewer (7.14). Optional in the schema so a file written before the taxonomy loads; required by the loader on a dataset whose manifest carries the `taxonomy` block |
| `subject` | `list[str]`, 1..4, unique, **in tagger precedence order** (the first is the primary subject, the cohort key of 18.5), **optional** as above | the fine topic under the category, values of the `subject` facet of `tags.v1.json` (7.14) |
| `structure` | `str`, a value of the `structure` facet, **optional** as above | the question's shape (`threshold-above`, `by-date`, `head-to-head`, ...), which decides whether two markets are comparable at all (7.14) |
| `horizon` | `str`, one of `intraday`, `week`, `month`, `quarter`, `year-plus`, **optional** as above | derived from `close_at_ms - created_at_ms` by 7.14's boundaries, never from provider text and never from `resolved_at_ms` |
| `wiki_subjects` | `list[str]`, each 1..256 chars, `<= 8`, sorted, unique | the market's Wikipedia subject page titles as the importer read them, verbatim (capitals, spaces, colons and parentheses kept); the linker's `shared_links` compares against this list, never against `tags` |
| `currency` | `"usd"` or `"mana"` | `mana` iff `provider == "manifold"` |
| `source` | `"imported"` or `"reconstructed"` | `reconstructed` is refused by `seal` |
| `created_at_ms` | int | `< close_at_ms` |
| `close_at_ms` | int | `<= resolved_at_ms`; the venue's published close (Kalshi `close_time`, Manifold `closeTime`) |
| `resolved_at_ms` | int | the venue's settlement instant |
| `resolution` | `0` or `1` | |
| `resolution_source` | `str`, 0..500 | the venue's stated source, `"venue"` when unknown |
| `event_key` | `str` or `null` | Kalshi `event_ticker`, Manifold `groupSlugs[0]`, else `null`; the block key of section 12.3 |
| `interval_min` | `1`, `60` or `1440` (`1` is amendment C1c's minute grid, 18.3, ruling R241) | the grid of `bars` |
| `bars` | `list[Bar]`, `>= 2` | dense on the grid from `bar_of(created_at_ms)` to `bar_of(resolved_at_ms)` |
| `trades` | `list[Trade]` | sorted per section 3; may be empty for `reconstructed` |
| `first_price_bp` | int in `[1, 9999]` | the first quote or print; also the as-of price on a market's very first bar (section 5.4) |
| `final_price_bp` | int in `[1, 9999]` | the close of the **last** bar of the tape, next to settlement; never shown to agents, never named `last_price_bp` |
| `hardness_tags` | `list[str]` subset of `trivial, upset, whipsaw, illiquid`, sorted | section 7.5; never shown to agents |
| `quality` | object (`pmx.types.MarketQuality`) | `n_trades: int, unique_bettors: int|null, life_days: int, volume_milli_total: int, traded_bars: int`, plus `tape_kind: "prints"|"bars_only"` (ruling R167: `bars_only` when the provider publishes per-bar volume and no print tape, in which case `n_trades == 0` and `traded_bars` counts the bars with `volume_milli > 0`; the schema field is a contract issue of section 17.9) |
| `fee_schedule_id` | fee schedule id | section 8.8 |
| `wiki_subject_provenance` | `list["stated"|"derived"]`, `<= 8`, **optional** | one flag per entry of `wiki_subjects`, in the same order (ruling R169): `stated` for a subject the provider published or the sealed series map names, `derived` for one computed from the question or the title. Optional in the schema so that a file written before the flag existed still loads; an absent or empty list beside a non-empty `wiki_subjects` reads as every subject stated. The first of the five optional fields of this table (the taxonomy's four are amendment C1c's) |
| `notes` | `str`, 0..2000 | free text for humans |

`Bar`: `t_ms, open_bp, high_bp, low_bp, close_bp, vwap_bp` (all `[1, 9999]`, `low <= open, close, vwap <=
high`), `volume_milli >= 0`, `n_trades >= 0`, `yes_bid_bp: int|null`, `yes_ask_bp: int|null` (`bid <=
ask` when both present), `open_interest: int|null`.

`Trade`: `t_ms, price_bp in [1, 9999], size_milli >= 1, side in {"yes", "no", "unknown"}` (the taker's
side; Manifold `outcome`, Kalshi `taker_side`).

**`Bar` and `Trade` are the one in-memory shape for every kind** (amendment C1b, ruling R173). A continuous
instrument's file stores `_ticks` fields (`instrument.v1.json`, section 17.1) and the loader maps them onto
`Bar` and `Trade` field by field (`open_bp <- open_ticks`, `high_bp <- high_ticks`, `low_bp <- low_ticks`,
`close_bp <- close_ticks`, `vwap_bp <- vwap_ticks`, `yes_bid_bp <- bid_ticks`, `yes_ask_bp <- ask_ticks`,
`open_interest <- open_interest_milli`, `price_bp <- price_ticks`), so `MarketView.bars`, `quote_bar`,
`bar_at`, `bars_before` and `half_spread_ticks` take one type whose `_bp` fields carry the instrument's
ticks, exactly as R148 keeps one event shape per name. `Trade.side` is `yes`, `no` or `unknown` on a binary
and `buy`, `sell` or `unknown` on a continuous instrument; `TRADE_SIDES` carries the five and the loader
enforces the pair per kind. The `[1, 9999]` bounds above are the binary bounds, enforced by the loader on a
binary and widened to `1..PRICE_TICKS_MAX` on a continuous instrument (ruling R148).

`final_price_bp` is the one field of this table whose name changed after the adversarial review:
`MarketView.last_price_bp` (section 8.3) is the **as-of** price of the bar being decided, and a `Market`
field of the same name made `MarketView(last_price_bp=market.last_price_bp)` a leak that no named test
would have caught. The two names are now disjoint, and E1's leak test asserts
`"final_price_bp" not in canonical_json(obs.to_dict())`.

**`Market` is the binary `Instrument`** (amendment C1b, section 17.1, ruling R144). It keeps every field of
this table, in code, in `market.v2.json` and on disk, and satisfies the common `Instrument` base through
the view `Market.instrument`: `kind = "binary"`, `vendor = provider`, `symbol = provider_id`,
`tick_size_micro = 100`, `point_value_micro = 1_000_000`, `session_calendar_id = "continuous"`,
`borrow_schedule_id = carry_schedule_id = None`, `listed_at_ms = created_at_ms`, `delisted_at_ms =
resolved_at_ms`, `short_allowed = True`. A continuous instrument is a `ContinuousInstrument` under
`instrument.v1.json` in `instruments/<id>.json` and never a `Market`. Two provenance rules of the data
gate are recorded here because the data package is implementing them now: every provider populates
`wiki_subjects` and marks each entry `"stated"` or `"derived"` in the parallel `wiki_subject_provenance` list
(ruling R169: Kalshi from the sealed `src/pmx/lexicons/kalshi_series_subjects.v1.json` map plus
title-derived candidates, Manifold from the capitalised token runs of the question, deduplicated), and a
Kalshi `category` comes from the sealed series-ticker map `src/pmx/lexicons/kalshi_series_categories.v1.json`
with `other` as the fallback, counted in the manifest (ruling R170). `quality.tape_kind` and
`wiki_subject_provenance` are in `market.v2.json` already, landed by the data package in the same pass.

Two methods of the `Instrument` base, and so of `Market` and `ContinuousInstrument` alike (ruling R173), are
part of the contract because the engine calls them by name (D1 owns both):

```python
def bar_at(self, t_ms: int) -> Bar | None: ...            # the bar whose t_ms == bar_of(t_ms, self.interval_min)
def bars_before(self, now_ms: int, limit: int) -> tuple[Bar, ...]: ...
    # the last `limit` bars with b.t_ms + interval_ms <= now_ms, oldest first; () when none is completed
```

`MarketMeta` (D1) is the leak-free projection of a market that the metrics and the optimizer pass around
instead of the market itself:

```python
@dataclass(frozen=True, slots=True)
class MarketMeta:
    id: str; provider: str; category: str; tags: tuple[str, ...]; event_key: str | None
    created_at_ms: int; close_at_ms: int; resolved_at_ms: int; resolution: int
    interval_min: int; n_bars: int; hardness_tags: tuple[str, ...]; fee_schedule_id: str; fold: str
    kind: str = "binary"                # amendment C1b, ruling R144: one of INSTRUMENT_KINDS
    # Amendment C1c (7.14, 18.5, rulings R265 and R266): the taxonomy and the cohort, defaulted so a meta of a
    # dataset built before the taxonomy is what it was. None of the five reads a field of 7.9, so every one of
    # them may sit in a MarketView and in a rule's scope at every bar.
    subject: tuple[str, ...] = ()       # tagger precedence order; subject[0] is the primary subject
    structure: str = ""                 # "" on an untagged dataset, else a structure facet value
    horizon: str = ""                   # "" on an untagged dataset, else intraday | week | month | quarter | year-plus
    provider_labels: tuple[str, ...] = ()
    cohort_id: str | None = None        # the one cohort of 18.5, None for platform-meta, other and untagged markets
    # On a continuous instrument (ruling R186): created_at_ms = listed_at_ms; resolved_at_ms = delisted_at_ms
    # when set, else the dataset's window end_ms; close_at_ms = resolved_at_ms; resolution = -1;
    # event_key = None; hardness_tags = (); fold = "all"; n_bars = the number of bars of the file. The
    # canonical order of section 3, block_key of 12.4 and Folds of 12.7 read these values and nothing else,
    # so every package that iterates instruments "in canonical order" iterates the same sequence. The
    # collapse is one-way and this meta therefore carries no delisted_at_ms: the calendar's listed(i, t)
    # and last_bar(i) (17.2) read Dataset.market(id).instrument.delisted_at_ms, where None means listed to
    # the end of the run, and never resolved_at_ms (ruling R228).
```

`Dataset` (D1, the return type of `load_dataset`) is what `run_backtest` receives:

```python
@dataclass(frozen=True, slots=True)
class Dataset:
    manifest: DatasetManifest
    metas: tuple[MarketMeta, ...]                          # canonical order, section 3
    path: Path
    def market(self, market_id: str) -> Instrument: ...    # loaded and validated on demand; a continuous
        # instrument comes back CLIPPED at manifest.split.validation_end_ms (bars, trades, cash_events) so
        # no consumer outside the claim path ever holds the sealed months of a price path (ruling R182)
    def sealed_market(self, market_id: str) -> Instrument: ...   # the unclipped record; named only here,
        # where it is declared, and in optimizer/folds.py and optimizer/claims.py (architecture rule 3
        # scans for it, rulings R182 and R223)
    def news_for(self, market_id: str, now_ms: int) -> tuple[NewsItem, ...]: ...   # visible_from_ms <= now_ms
    def news_global(self, now_ms: int) -> tuple[NewsItem, ...]: ...
    def calendar(self, calendar_id: str) -> SessionCalendar: ...   # amendment C1b, section 17.2 (sealed);
        # "continuous" is synthesised (one session [0, INT63_MAX)) and never read from a file (ruling R185)
    @property
    def purpose(self) -> str: ...      # "research" | "showcase" (5.6, ruling R263); replaces is_demo_pack, which is deleted
    @property
    def cohorts(self) -> tuple[Cohort, ...]: ...   # pmx.cohorts.list_cohorts(self.metas), sorted by cohort_id (18.5);
        # () on a dataset built before the taxonomy; the loader refuses a manifest whose cohort rows disagree
        # with the folds it recomputes (FoldIntegrityError, ruling R266)
```

`market(market_id)` returns a `Market` for a binary and a `ContinuousInstrument` for every other kind;
both satisfy `Instrument` (section 17.1) and `metas` carries one `MarketMeta` per instrument of every
kind, with `kind` on it. A continuous instrument returned by `market` carries no bar, trade or cash event
with `t_ms >= validation_end_ms` (ruling R182): a binary's sealed guarantee is structural, because a sealed
id is never handed out, and a continuous instrument belongs to every fold (17.6), so its guarantee is the
clip. `sealed_market` returns the whole record and joins `open_sealed_test` and `_sealed_ids` in the scan
of architecture rule 3, so the sealed months of a price path are reachable from `claims.py` and nowhere
else. `quality` stays a whole-window build statistic (the filters of 7.4 need the whole life, as they do on
a binary whose life ends in the sealed fold) and is never shown to an agent (7.9).

Kalshi fields map: `yes_bid`/`yes_ask` in cents become bp times 100; candlestick `price.close` and
friends likewise; `volume` contracts become `volume_milli = volume * 1000`. Manifold arrives as JSON
**numbers**, not as decimal strings (verified against the live API on 2026-09-07: `"probAfter": 0.9791195212815591`), so `json.loads` would turn every price into a binary float before an importer could object. A money provider's body is therefore read with
`HttpClient.get_text` and parsed with `json.loads(body, parse_float=Decimal)`, and a `float` reaching a
conversion raises `MalformedResponseError`. The conversion itself is exact and never a float:
`probAfter` becomes `bp_from_ppm(round_half_up_decimal(Decimal(prob_after) * PPM_ONE))` and `amount` in
mana becomes `size_milli = round_half_up_decimal(Decimal(amount) * 1_000)`.

### 7.3 NewsItem (`news.v1.json`, `pmx.types.NewsItem`)

| Field | Type | Rule |
|---|---|---|
| `schema_version` | `"news.v1"` | |
| `news_id` | news id | section 2 |
| `source` | `wikipedia_current_events`, `wikipedia_asof`, `wayback`, `gdelt`, `manifold_comment`, and amendment C1b's `edgar`, `fred`, `cboe` (17.7), and amendment C1c's `hn` (18.3, ruling R241) | `NEWS_SOURCES`; each carries a granularity and a default lag in `SOURCE_GRANULARITY_MS` and `SAFETY_LAG_MS_BY_SOURCE` (18.3) |
| `kind` | `headline`, `background`, `frontpage`, `article`, `comment`, `filing`, `release`, `story` | `wce -> headline`, `wasof -> background`, `wb -> frontpage`, `gd -> article`, `mfc -> comment`, `edg -> filing`, `fred` and `cboe -> release`, `hn -> story` for a Hacker News story and `comment` for one of its comments |
| `published_at_ms` | int | `<= freeze_ms`; for `wce` the timestamp of the first revision of the day page that carries the bullet, with the end of the page day as the fallback (section 5.5, decision D-R3, ruling R249); for `hn` `created_at_i * 1_000` |
| `published_at_source` | `"revision"` or `"page_day"` or `null`, **optional** | `wce` only: which of 5.5's two stamps `published_at_ms` is; `null` for every other source and absent on a file written before decision D-R3 |
| `revid` | `int` or `null` | required non-null for `source == "wikipedia_asof"`: the MediaWiki revision id the text came from, so the snapshot is auditable against the API; for a `wce` bullet stamped from its revision, the id of that revision (ruling R249) |
| `asof_day` | `str` (`yyyy-mm-dd`) or `null` | required non-null for `source == "wikipedia_asof"`: the day the fetch asked for. The loader refuses `published_at_ms > day_start_ms(asof_day) + MS_PER_DAY` |
| `visible_from_ms` | int | `== published_at_ms + lag(source)`, where `lag(source)` is `manifest.news.safety_lag_by_source[source]` when the manifest carries the block and `manifest.safety_lag_ms` otherwise (section 5.5, ruling R241); the loader recomputes and refuses a mismatch |
| `fetched_at_ms` | int | wall clock of the fetch; allowed here because a dataset is built, not run |
| `url` | `str` | |
| `headline` | `str`, 1..300 | |
| `text` | `str`, 0..4000 | body, bullet text, comment text |
| `section` | `str` or `null` | Current events section slug (`armed_conflicts`, `politics`, `business`, ...) |
| `wiki_links` | `list[str]`, `<= 32`, sorted, unique | article titles |
| `source_urls` | `list[str]`, `<= 16` | |
| `match_ids` | `list[market id]`, sorted, unique | markets the item is linked to |
| `match_scores_permille` | `list[int]`, same length as `match_ids` | the linker's score per link (section 7.6) |
| `lang` | `"en"` | |
| `author_key` | `str` or `null` | for comments: `sha256(user_id)[:16]`, never the user name |

### 7.4 Window and quality filters (D6, all in `BuildConfig`, all reported)

Defaults are constants in `pmx.types`; every filter reports `removed_count` in the manifest.

```python
@dataclass(frozen=True, slots=True)
class BuildConfig:                                  # D6; every field enters manifest.filters.config
    freeze_date: str                                # "yyyy-mm-dd"; freeze_ms = day_start_ms(freeze_date)
    providers: tuple[str, ...]                       # sorted, section 2
    interval_min: int = 1_440
    window_days: int = 365
    opened_early_days: int = 90
    min_trades: int = 50
    min_unique_bettors: int = 30
    min_life_days: int = 7
    min_traded_bars_per_day_permille: int = 250
    exclude_self_resolved: bool = True
    exclude_kalshi_shards: bool = True
    kalshi_series_allow_list: tuple[str, ...] = ()   # asked of the provider, ruling R100
    instruments: tuple[str, ...] = ()                # amendment C1c (18.3, ruling R298): sorted, unique vendor
                                                     # symbols (17.1); the minute build's explicit list
    safety_lag_ms: int = SAFETY_LAG_MS_DEFAULT
    news_sources: tuple[str, ...] = ("wikipedia_current_events", "manifold_comment")
    limit_per_provider: int | None = None           # applied AFTER the window walk, stratified by month (R168)
    kinds: tuple[str, ...] = ("binary",)            # amendment C1b, section 17: the instrument kinds imported
    min_traded_bars: int = 20                        # ruling R167: the bars-only proxy of the min_trades filter
    # Amendment C1c (section 18, decisions D-R13, D-S3, D-S4; rulings R258, R262, R263, R298). __post_init__
    # refuses window_days > WINDOW_DAYS_MAX = 730 (5.6), interval_min outside INTERVALS_MIN, on interval_min == 1
    # a news source whose SOURCE_GRANULARITY_MS exceeds MINUTE_SOURCE_GRANULARITY_MAX_MS (18.3), and on
    # interval_min == 1 an empty `instruments` AND an empty `kalshi_series_allow_list`, all InvalidConfigError.
    purpose: str = "research"                        # "research" | "showcase" (5.6); written into every manifest
    universe_min_settled: int = 5                    # the documented universe rule of D-R13, below: defaults the first
    universe_min_volume_cents: int = 100_000         # build reports against, not laws
    def to_dict(self) -> dict[str, object]: ...      # manifest.filters.config, canonical
```

`manifest.filters.removed` carries **exactly** these ten keys, every one of them always present and `0`
when the filter removed nothing, so the UI's dataset panel and the gate's shortfall report can be written
against a fixed shape: `window`, `opened_early`, `binary`, `min_trades`, `min_life`, `density`,
`self_resolved`, `kalshi_shards`, `resolution`, `no_leak`.

| Filter | Default | Rule |
|---|---|---|
| window | `window_days = 365`, refused above `WINDOW_DAYS_MAX = 730` (5.6, ruling R262) | `freeze_ms - window_days d <= resolved_at_ms < freeze_ms - 1 d`; not applied to a `purpose: "showcase"` build (ruling R263) |
| opened early | 90 days | `created_at_ms >= window_start_ms - 90 d` |
| binary | always | one YES/NO leg; multi-outcome events imported as their binary legs each with its own id |
| min trades | `50` | `quality.n_trades >= 50` **or** `quality.unique_bettors >= 30` **or** (`quality.tape_kind == "bars_only"` **and** `quality.traded_bars >= min_traded_bars`, default `20`). The third clause is ruling R167: Kalshi publishes no settled print tape (`GET /markets/trades` answers nothing for a settled ticker) while its candlesticks carry per-bar volume and open interest, so a bars-only provider carries `tape_kind = "bars_only"`, `n_trades = 0` and a real `traded_bars`, fills under 8.6 on bar volume exactly as before, and is accepted on that count. This is distinct from ruling R105's Polymarket case, whose tape carries no volume at all and which stays out |
| min life | `7` days | `resolved_at_ms - created_at_ms >= 7 d` |
| density | `250` permille | `quality.traded_bars * 1000 >= min_traded_bars_per_day_permille * life_days` on the daily grid. The PRD says one traded bar per day (1000 permille); the default is lowered to one every four days and reported, see decision D-3 |
| creator-resolved | on | Manifold: refuse when `resolution_source == "creator"` (`Market` has no `resolverId`, ruling R101). Creator resolution is Manifold's normal mechanism, so a Manifold build passes `--keep-self-resolved` or loses the whole provider |
| Kalshi shards | on | refuse tickers matching `^KXMVE` and any series in `KALSHI_EXCLUDED_SERIES` (data, D2) |
| per-provider cap | none | `limit_per_provider`, applied **after** the window walk by deterministic stratified sampling across the window's twelve months (ruling R168): quota `limit // 12` per month, the remainder (and any quota a thin month cannot fill) to the busiest months by pre-cap count, ties to the earlier month; inside a month the ids are drawn with `sample_without_replacement` from the one `dataset.subsample` substream of `RngTree(sample_seed_for(name))`, `sample_seed_for(name) = derive_seed(0, f"dataset/{name}") % SEED_SPACE`, providers in sorted order and months in order. Every fold of 12.7 is therefore populated by construction, and the manifest records the pre-cap count per provider and month (`counts.precap_per_provider_month`, twelve integers per provider). The earlier behaviour, each importer capping from its own end of the window, gave one provider the first two days and the other the last thirteen (`docs/BUILD_STATE.md` 5.3) |
| kinds | `("binary",)` | `kinds`: which instrument kinds the build imports (section 17.1); a continuous kind's instruments are filtered by `min_life_days` and `density` on their own calendars and by nothing else in this table |
| Kalshi series | the documented universe rule (decision D-R13, ruling R258) | **The series list is an output of the builder, not an input.** From the settled walk the builder keeps every Kalshi series (the ticker prefix before the first dash) with at least `universe_min_settled` settled markets in the window and at least `universe_min_volume_cents` of volume, and writes the manifest's `universe` block (7.8): the rule, every series with its counts before and after the quality filters and its volume, `n_series_before` and `n_series_after`. Weather series are kept and carry the builder label `forecastable_from_public_models` in `tags` (7.14). `kalshi_series_allow_list` stays as a **debug narrowing** only (empty by default; it is still what is passed to the provider as `series_ticker`, the only narrowing either settled listing honours, ruling R100, so the builder passes the universe it listed). The 731 series of the first build were picked by hand and were category-biased; a universe a reader cannot recompute is not a denominator |
| resolution | always | `resolution` in `{0, 1}`; Manifold `MKT`, `CANCEL`, `N/A` refused |
| no leak | always | `resolved_at_ms < freeze_ms`, every news `published_at_ms <= freeze_ms` |

**The build target is stated in cohorts, per venue, and the market count follows** (decisions D-S1,
D-S11 and D-S12 in the form section G of `docs/REVIEW_2026-09-09_SCALE_TAGS.md` corrected them; rulings
R260, R270, R271). A research build must reach `KALSHI_COHORT_TARGET = 40` usable cohorts on Kalshi
(`n_train >= COHORT_MIN_TRAIN = 30`, 18.5) and `MANIFOLD_COHORT_TARGET = 8` on Manifold, whose role is
breadth and print-tape depth rather than comparative analysis (the prototype tagger found zero Manifold
cohorts of ten and no dense question templates to concentrate). The market floor is what the cohort target
costs: about **7 000 Kalshi markets** on the measured distribution, against a reachable in-window listing of
about 15 000 rows living a week or more (`docs/BUILD_STATE.md` 7.5), and 2 000 Manifold markets (decision
D-R7's number, kept as Manifold's floor). The builder reports the reachable count against the target
**before** building (`pmx data build --plan`), and when the 365-day window cannot deliver it the fallback
order is fixed in advance: **first** widen `window_days` toward `WINDOW_DAYS_MAX` (5.6), **then** relax
`min_trades` and `min_traded_bars` with the count removed stated per filter, and **only last** lower the
cohort target, each step recorded with its reason in `manifest.build.fallbacks`. Widening the window costs
contamination risk for LLM agents alone, which the clean-market rule of 11.5 handles; lowering the cohort
target costs the comparison itself, which nothing else recovers. **`build.status` is per venue** (ruling R290, the form R270 states): a build below `KALSHI_COHORT_TARGET`
on Kalshi is a **failed** build (`manifest.build.status = "failed"`, the shortfall per filter and per
venue beside it) and gate G3 fails on it; a build that misses only `MANIFOLD_COHORT_TARGET` is
`status = "ok"` with `build.shortfall.manifold` filled, and gate G3 records it. Manifold's role is
breadth and print-tape depth, so its shortfall costs breadth and not the comparison, which is why R270
declines to fail a build on it. The
per-provider cap of ruling R168 stays lifted and is a debug option. AC-11 of
`docs/PRD_V3_TRADING_OPTIMIZER.md` is corrected in place to this statement (ruling R260).

### 7.5 Hardness tags (computed by D6, stored, never used to drop, never shown to agents)

| Tag | Definition |
|---|---|
| `trivial` | every bar's `close_bp` stayed inside `[500, 9500]`... no: **never left** `[500, 9500]` means the market was never extreme; the PRD's `trivial` is the opposite. Normative: `trivial` iff every `close_bp` is `< 500` or every `close_bp` is `> 9500` **from the first bar** (the outcome was never in doubt) |
| `upset` | the mean `close_bp` over the last 30 days of life (or the whole life if shorter) is on the wrong side of `5000`: `> 5000` with `resolution == 0` or `< 5000` with `resolution == 1` |
| `whipsaw` | more than four crossings of `5000` by consecutive bar closes |
| `illiquid` | median daily `volume_milli` is in the bottom decile of the dataset's provider slice (computed after the filters, so it is relative and reported with the decile boundary) |

Decision D-4 records the `trivial` correction: the PRD's parenthesis ("never left [500, 9500]") describes
a market that never became certain, which is the hard case, not the trivial one.

### 7.6 The linker (D5)

Deterministic, integer and stored:

```python
keyword_overlap = round_half_up(1_000 * len(K_item & K_market), len(K_market)) if K_market else 0
link_overlap    = round_half_up(1_000 * shared_links, max(1, len(item.wiki_links)))
# ruling R169: the two weights are renormalised over the evidence the MARKET actually carries
if market.wiki_subjects:   match_score_permille = (600 * link_overlap + 400 * keyword_overlap) // 1_000
else:                      match_score_permille = (1_000 * keyword_overlap) // 1_000    # 1000 permille on keywords
# every branch lands in [0, 1000]
```

The first branch is the v2 formula, `round_half_up(600 * shared_links, max(1, n_links)) + (400 *
keyword_overlap) // 1_000`, to the unit. The renormalisation is ruling R169: on the first real dataset
392 of 400 Manifold markets and every Kalshi market carried no `wiki_subjects`, so the 600-permille term
was zero for effectively every market, no score could exceed 400, and the 7 391 Current events items
linked to nothing (`docs/BUILD_STATE.md` 5.4). A market with no subjects is now scored on keyword overlap
alone at 1000 permille (a market with subjects keeps the 600/400 split whatever its keyword set), and every
provider populates `wiki_subjects` (section 7.2) so the first branch
is the common one again; a derived subject is marked `"derived"` in `wiki_subjects_source` and counts
in `shared_links` exactly as a stated one, the flag (`wiki_subject_provenance`) being for the reviewer,
not the score.

`shared_links` counts item `wiki_links` equal to an entry of the market's `wiki_subjects` (section 7.2;
never `tags`, whose pattern forbids the spaces every real article title has). `K_item` and `K_market` are
the lowercase alphabetic tokens of length `>= 4` of the item's headline plus text and of the market's
question plus tags, minus a stop list shipped as `src/pmx/lexicons/stopwords.v1.json`. Both terms are
permille and the sum is in `[0, 1000]`, which is what `news.v1.json` and
`LINK_THRESHOLD_PERMILLE = 150` assume; the earlier spelling with `/` and a bare `400 * keyword_overlap`
reached 400 600 and was a float. Items with score `< LINK_THRESHOLD_PERMILLE` are not linked. Scores are
stored, so a reviewer can audit every link.

D5 ships exactly `stopwords.v1.json`, `paraphrases.v1.json` (`{"paraphrases": [str, str, str]}`, used by
A6's contamination prompt) and **one lexicon per category of section 2**, in that fixed order, so
`LEXICON_COUNT = 12` is a constant in `pmx.types` and `newsbayes.lexicon_id` is `0..11` (section 10.5)
without A1 having to count D5's files. A lexicon file that is missing means no hits, never a crash.

**The linker's precision is measured, and a weak build says so** (decision D-R4, ruling R250). Per build,
`LINKER_AUDIT_N = 50` links are drawn with `sample_without_replacement` from the `dataset.subsample`
substream over every `(news_id, market_id)` link of the dataset and written to
`audits/<dataset_hash[:16]>/linker.json` as `{dataset_hash, sample_seed, n, links:
[{news_id, market_id, score_permille, verdict: "correct" | "wrong" | "unsure" | null, reviewer}],
precision_permille}`, where the verdicts are a human's (gate G3 performs the review) and
`precision_permille = round_half_up(1_000 * n_correct, n_correct + n_wrong)`; `pmx data audit-links` writes
the file with `null` verdicts and recomputes the precision once they are filled. The manifest's
`news.linker_audit {path, n, precision_permille}` reports it (7.8), and a dataset whose precision is below
`LINKER_PRECISION_MIN_PERMILLE = 800` carries `news_links: "weak"`: every leaderboard row of a run whose
roster bought a news sensor (18.1) carries `news_links:weak` in `LeaderboardRow.labels` (12.10). The file
is outside the dataset hash because the audit happens after the seal; it is keyed by the hash it audits.
**It lives in `audits/`, which is tracked** (ruling R296), for the reason `claims/` and `rules/` are
(12.7: the ledger is evidence): fifty human verdicts are the least reproducible artefact of a build wave
and the sole evidence behind a label gate G3 reads, and `data/datasets/` is git-ignored, so an audit
written there is one `rm -rf` from having to be redone.

### 7.7 Split (D6, section 12.7 defines the folds)

```python
month_edges_ms = [window_start_ms + ((k * 365) // 12) * MS_PER_DAY for k in range(13)]
# offsets in days: 0, 30, 60, 91, 121, 152, 182, 212, 243, 273, 304, 334, 365 (window_days = 365; the
# formula reads window_days in place of 365 on a wider window, still thirteen edges)
# The two headline cuts are COUNT QUANTILES of GROUP resolution order (decision D-R1, rulings R247 and
# R290): not month edges, and not the market's own resolution instant.
def group_of(m):        # the market's EventCluster (16.3), else its Kalshi event_key group, else {m}
    ...
def fold_key_ms(m):     # ruling R290: the count quantile and the cluster rule are ONE operation
    return bar_of(max(x.resolved_at_ms for x in group_of(m)), interval_min)
ordered = sorted(binaries, key=lambda m: (fold_key_ms(m), m.resolved_at_ms, m.id))
n = len(ordered)
k_train = (n * FOLD_QUANTILES_PERMILLE[0]) // 1_000       # FOLD_QUANTILES_PERMILLE = (600, 800): 60 / 20 / 20
k_validation = (n * FOLD_QUANTILES_PERMILLE[1]) // 1_000
train_end_ms = fold_key_ms(ordered[k_train])              # a bar open, so a run can clip to it
validation_end_ms = fold_key_ms(ordered[k_validation])
# train: fold_key_ms(m) < train_end_ms; validation: train_end_ms <= fold_key_ms(m) < validation_end_ms;
# sealed test: validation_end_ms <= fold_key_ms(m), with resolved_at_ms < freeze_ms - 1 d throughout.
# Every market of a group whose fold key is the cut bar goes to the LATER fold, so the realised counts
# differ from k_train and n - k_validation by the ties of one bar and by nothing else; the manifest
# reports the realised counts AND the realised permille beside the target quantiles.
```

The calendar thirds this section used to cut gave the first real dataset 111 train, 46 validation and 130
sealed markets, an inverted pyramid (`docs/REVIEW_2026-09-08.md`); count quantiles are still chronological
(a train market always resolved before a validation one, which before a sealed one) and put the mass where
the fitting is. **Folds are cluster-aware** (decision D-R2, ruling R248): a market's fold is decided by
`fold_key_ms`, the resolution bar of the **latest-resolving** member of its `EventCluster` (16.3) or of
its Kalshi `event_key` group, because a train price path may otherwise encode a sealed outcome that the
cross-asset sensor, a cluster feature or a hive resolution would carry.

**The cluster rule is inside the cut, not applied after it** (ruling R290). Cutting on the market's own
resolution and then moving each group to its latest member's fold moves markets **one way only**, always
later, without bound: the train fold can only lose and the sealed fold can only gain, the drift is largest
exactly on the dense Kalshi `event_key` groups the cohort target of 7.4 is built from, and the inverted
pyramid D-R1 was written to fix comes back silently. Cutting the quantiles on `fold_key_ms` gives the same
folds the two-step rule intended, with the 60/20/20 shares held by construction and no move afterwards.
`manifest.split.cluster_moves` keeps the same shape and reports every market whose own resolution bar
falls in an earlier fold than its `fold_key_ms` (`{market_id, from_fold, to_fold, group_id}`, a
`cluster_id` or the `event_key`), the loader recomputes them and refuses a mismatch, `pmx data verify`
checks that no group spans two folds, and `make_folds`, the rule tester and `claim` refuse a dataset whose
folds split a group with `FoldIntegrityError` (13.1). `make_folds` also raises `FoldIntegrityError` when a
fold is **empty** after the cut, since every paired bound and every `usable_for_paired_test` depends on
all three being populated. A cohort (18.5) is **not** such a group (ruling R293): its markets keep the
folds this cut gave them, and its three per-fold counts are what those folds left.

A binary belongs to exactly one fold, by its group's latest resolution and therefore by its own too (a
train market still always resolves before `train_end_ms`, because `resolved_at_ms <= fold_key_ms`). The
manifest stores the thirteen edges (still the rolling folds' edges), the two cuts with
their dates, the quantiles, the moves, the three realised counts and `split.realised_permille` (7.8). A continuous instrument belongs
to every fold whose span intersects `[created_at_ms, resolved_at_ms)` of its `MarketMeta` (amendment
C1b, rulings R162 and R186; 17.6), where a fold's span is `[window_start_ms, train_end_ms)`,
`[train_end_ms, validation_end_ms)` and `[validation_end_ms, freeze_ms - MS_PER_DAY)`: the test needs no
bar and no sealed file, and a run on a fold clips its `t0_ms` and `t1_ms` to the fold's span. The
**rolling folds** of 12.7 (`train 1..k, validate k+1`) keep the month edges: they are the patience
criterion's and the rule tester's rolling pair (18.2), and a month is the unit a reader can name. They are
**clipped to the training fold** (ruling R277): only the `k` in `4..9` whose month `k + 1` ends at or
before `train_end_ms` are kept, so `Folds.rolling` may hold fewer than six pairs and never one that
replicates on a validation or a sealed market. When it would hold **none** (a training fold shorter than
six months of calendar), `make_folds` raises `FoldIntegrityError` and the build's remedy is the fallback
order of 7.4, first of which is a wider `window_days`.

### 7.8 Manifest, seal and verify (`dataset.v1.json`)

```
schema_version "dataset.v1", name, freeze_date, freeze_ms, window {start_ms, end_ms}, interval_min,
providers[], safety_lag_ms, filters {config: {...}, removed: {<filter>: count}},
counts {markets, per_provider {..}, per_category {..}, resolution_yes, resolution_no, hardness_tags {..}},
news {sources: [{source, n_items, fetched_at_ms_min, fetched_at_ms_max}], n_items, n_linked},
split {month_edges_ms[13], train_end_ms, validation_end_ms, n_train, n_validation, n_sealed},
files [{path, sha256, bytes}], dataset_hash, built_by {pmx_version, contract_version, rng_algorithm_version},
sealed: bool, notes,
clusters {matcher_version, min_score_permille, resolution_tolerance_ms, overrides_sha256, n_clusters,
          n_clusters_asof, n_cross_venue, n_constraints, per_kind {sum_to_one, implies, monotone_ladder,
          complement}, n_markets_clustered}                              optional, section 16.3, ruling R117
impact {fit_fold: "train", fit_t1_ms, params_sha256, impact_bp_per_pct_by_decile[10], n_markets_fit}
                                                                         optional, section 16.1, ruling R135
kinds [..], instruments {per_kind, per_provider, per_vendor, n_cash_events {per_kind}, n_calendars},
schedules {fee [ids], borrow [ids], carry [ids]},
counts.precap_per_provider_month {provider: [12 ints]}, counts.n_bars_only, counts.n_category_fallback,
split.n_instruments_train, split.n_instruments_validation, split.n_instruments_sealed
                                                                         amendment C1b, sections 17.2, 17.6,
                                                                         17.9; rulings R149, R168, R170;
                                                                         applied by gate G2 (R201)
purpose: "research" | "showcase",  window_days: int,  resolution_span {min_ms, max_ms}          5.6; rulings R262, R263
split.method: "count_quantile", split.quantiles_permille [600, 800], split.train_end_date, split.validation_end_date,
split.cluster_moves [{market_id, from_fold, to_fold, group_id}], split.n_moved,
split.realised_permille [train, validation, sealed]                              7.7; rulings R247, R248, R290
news.safety_lag_by_source {source: ms}, news.linker_audit {path, n, precision_permille} | null   5.5, 7.6; rulings R241, R250
universe {rule: {min_settled, min_volume_cents}, series: [{series, n_settled, n_kept, volume_cents, labels}],
          n_series_before, n_series_after}                                                 7.4; ruling R258
taxonomy {version, lexicon_sha256, series_facets_sha256,
          per_venue {provider: {subject_coverage_permille, structure_coverage_permille, n_distinct_subjects,
                     n_other_subject, n_other_structure, n_platform_meta, n_cohorts, n_cohorts_usable,
                     label: "ok" | "weak"}},
          cohort_size_histogram {"1", "2-4", "5-9", "10-29", "30+"}, audit {path, n, precision_permille} | null}
                                                                         7.14; rulings R265, R267, R268
cohorts [Cohort.to_dict() ...]  (every field of 18.5's Cohort but market_ids, sorted by cohort_id)   18.5; ruling R266
build {status: "ok" | "failed", targets {kalshi_cohorts, manifold_cohorts, kalshi_markets, manifold_markets},
       reachable {provider: n}, shortfall {provider: {filter: n}}, fallbacks [{step, from, to, reason}]}
                                                                         7.4; rulings R260, R271
                                                                         every block of this group is optional in
                                                                         `dataset.v1.json` (a manifest written before
                                                                         amendment C1c has none) and written by every
                                                                         build from DS1 on
```

The last two blocks are absent from a dataset built with no cluster matcher and no impact calibration, and
`dataset.v1.json` makes both optional for that reason. `clusters/` is inside the walk of 4.3, so the two
files it holds are covered by `dataset_hash` and neither carries a `dataset_hash` of its own (ruling
R128). The `impact` block is fit on the training fold and says so in `fit_fold` and `fit_t1_ms`, so a
claim can refuse a calibrated run whose calibration ran past its own `t0_ms` (ruling R135).

A dataset carries one `interval_min` and every market of it carries the same one (section 5.3), so an
hourly headline claim is a **second dataset** built with `interval_min = 60`, with its own hash, its own
folds and its own claims.

`pmx data seal` (D1's `seal_dataset(path)`): refuses any `reconstructed` market (`SealError`), recomputes
`files` and `dataset_hash` over `markets/`, `news/`, `wiki_asof/`, `clusters/`, `instruments/`,
`calendars/` and `taxonomy/` (the middle two are amendment C1b's, ruling R149, applied to the loader by gate
G2; `taxonomy/` is amendment C1c's, ruling R267; an absent directory adds no line, so no hash of
2026-09-09 moves), writes `sealed: true`. `pmx data verify` also checks, on a manifest that carries
`split.cluster_moves`, that no cluster or `event_key` group spans two folds (`FoldIntegrityError`, ruling
R248), and on one that carries `cohorts`, that every cohort row matches the folds and facets it
recomputes (ruling R266). `pmx data verify` (`verify_dataset(path)`): recomputes
and raises `DatasetHashMismatchError` on any difference; `run_backtest` calls it before reading a single
market and refuses to start on failure. The demo pack carries `sealed: false` and a valid hash so it is
reproducible without being claimable.

### 7.9 Data leak rules

These fields exist in the dataset and **never** appear in an observation, a prompt or a research result:
`resolution`, `resolved_at_ms`, `resolution_source`, `final_price_bp`, `hardness_tags`, `quality`,
`n_bars`, `fold`, any bar with `t_ms + interval_ms > now_ms`, any trade with `t_ms >= now_ms`, any news
with `visible_from_ms > now_ms`, any hive entry with `visible_from_ms > now_ms`, any memory record with
`written_at_ms > now_ms`, any other agent's forecast on a market that has not settled.

Amendment C1 extends the list by every cluster-derived and detector-derived name, and the extension is
normative **here**, not only in the amendment (ruling R116): `cluster_id`, `constraint_id`, any
`MatchReason` (its `kind`, `asof`, `detail` and `score_permille`), a cluster's or a constraint's
`score_permille`, `asof`, `source` and `resolution_span_ms`, any entry of `clusters/overrides.json`, and
any field of an `OpportunityEvent` of section 16.4. Amendment C1b extends it again (section 17.3, rulings
R151, R181 and R183): `delisted_at_ms`, `last_bar(i)` and anything derived from it (the bars remaining, a
fold's edge), any `CashEvent` whose application bar has not completed at `now_ms` and every field of one
(`cash_event_id`, `rate_ppm`, `dividend_micro`, `numerator`, `denominator`, `gap_ticks`,
`from_price_ticks`, `to_price_ticks`, every `detail` key), `last_price_ticks`, `n_forecasts_unresolved`,
and a `price_realised_ticks` or a `realised_sign` of a horizon that has not resolved at `now_ms`. An
**applied** `CashEvent` (its application bar completed, `applies_at(e) + interval_ms <= now_ms`) is the
venue's published past and is visible through `MarketView.cash_events` exactly as a completed bar is
(ruling R183); `Dataset.sealed_market` is never called on the observation path (ruling R182). A venue's **fixed** schedule (funding
every eight hours, the sealed session calendar) is not on this list, because it is the venue's rule and
not a datum about the future. A cluster peer's **prices** are not on this list and
are visible exactly as any other market's are (section 16.3); what is forbidden is the grouping itself.

The list is **record-scoped** (ruling R209): no `MatchReason`, `EventCluster`, `Constraint`, `OpportunityEvent`
or unapplied `CashEvent` record reaches an observation, and 8.3's key scan bans their structural names, while
`kind`, `source`, `currency` and `market_ids` are legal keys of `NewsView`, `MarketView`, `CashEventView`,
`LessonView` and `NoteView` and are guarded by the poisoned-record test. Two subtrees are legal where they sit
and are set aside before the key scan: `HiveView.resolutions` (a settled market's published resolution carries
`resolved_at_ms`) and `MarketView.cash_events` (an applied event's verbatim `detail`, ruling R183).

The poisoned-future test (E1) injects one of each (including a memory record stamped after `now_ms`, one
of each cluster-derived name, a `CashEvent` whose application bar has not completed, a `delisted_at_ms` and
a `last_bar` value) and asserts by content match that none surfaces, and that a `CashEvent` applied before
`now_ms` does.

Amendment C1c adds to the list and says what is **not** on it (section 18, rulings R230, R239, R265, R266).
Added: a `HypothesisFamily`, a rule's test record, an `Insight` before its `visible_from_ms` (which is the
first bar after the last bar its promotion read, 18.2), a rule's live record beyond `now_ms`, and every
`SensorBlock` value of a bar that has not completed. Not on it, deliberately: a market's `subject`,
`structure`, `horizon`, `provider_labels` and `cohort_id` (7.14, 18.5), because they are computed from
`question`, `provider_id`, the sealed series map and the published life (`close_at_ms - created_at_ms`)
and never from `resolved_at_ms`, a bar or a resolution, so they are known before the market's first bar
and add no leak; and a sensor set, because it can only narrow what the filters above produced. The
poisoned-future test runs over **four named sets** (AC-26, ruling R298), because `tape` is mandatory and
"every sensor set" is two to the fourteenth: `SENSOR_SETS_UNDER_TEST = (("tape",), ("tape",) + every
market sensor, ("tape",) + every news sensor, SENSOR_NAMES)`, a constant beside E1's test, which asserts
the same content match on each; and S1's per-sensor test injects a future item of each sensor's source
and asserts the block does not move.

### 7.10 v1 migration identities (D1, `migrate_v1`)

The demo pack is the only committed dataset and the only tape wave 2 can run before G1, so the identities
the migration must hold are normative and are what `tests/test_contract_schemas.py` asserts on
`tests/fixtures/contract/market.demo-brexit-2016.json`:

1. the grid is daily and aligned: `interval_min == 1_440` and every `bar.t_ms % MS_PER_DAY == 0`;
2. bars are dense from `bar_of(created_at_ms)` to `bar_of(resolved_at_ms)` inclusive, one per day, no gap
   and no duplicate;
3. `first_price_bp == bp_from_v1_cents(v1.prices[0].price)` and
   `final_price_bp == bp_from_v1_cents(v1.prices[-1].price)`; a bar between two v1 control points carries
   the previous control point's price forward as `open == high == low == close == vwap`;
4. `source == "reconstructed"`, `provider == "demo"`, `id == f"demo-{v1_id}"`, `currency == "usd"`,
   `fee_schedule_id == "demo-zero"`, `trades == []`, `wiki_subjects == []`;
5. `volume_milli == 0` and `n_trades == 0` on every bar, because v1 has no volume (PRD 3.3). The demo pack
   is still tradable: section 8.6 step 1 exempts a `reconstructed` market from the volume rules rather than
   inventing a volume the source never had;
6. `hardness_tags` is computed by section 7.5 on the migrated bars, so Brexit carries `upset`.


### 7.11 The one HTTP client (D2, `pmx.data.importers._http`)

D2, D3, D4 and D5 are four wave-1 packages that all reach the network through this one class and nothing
else (decision D-11), so its surface is literal:

```python
DEFAULT_MIN_INTERVAL_MS = 1_000
HTTP_MAX_RETRIES = 3
HTTP_TIMEOUT_S = 30.0                      # a float, and one of the four legal float sites: never journaled
USER_AGENT_TEMPLATE = "pmx-research/{version} (contact: {contact})"
USER_AGENT_CONTACT_ENV = "PMX_USER_AGENT_CONTACT"
HTTP_PROXY_ENV = "PMX_HTTP_PROXY"

class HttpClient:
    def __init__(self, *, base_url: str, user_agent: str, min_interval_ms: int, cache_dir: Path,
                 max_retries: int = HTTP_MAX_RETRIES, timeout_s: float = HTTP_TIMEOUT_S,
                 api_key: str | None = None, proxy: str | None = None) -> None: ...
    def get_json(self, path: str, params: Mapping[str, str | int] | None = None, *,
                 cache: bool = True) -> object: ...
    def get_text(self, path: str, params: Mapping[str, str | int] | None = None, *,
                 cache: bool = True) -> str: ...
    def close(self) -> None: ...
```

- **User-Agent**: `USER_AGENT_TEMPLATE` filled with `pmx.__version__` and the contact address read from
  `PMX_USER_AGENT_CONTACT`; a fetcher that needs a contact address and finds the variable unset raises
  `NotConfiguredError` rather than sending a bare agent string (Wikipedia answers 403 to one).
- **Throttle**: at least `min_interval_ms` between two requests to the same `base_url`, measured by the
  client itself (the importers are the impure edge, so a monotonic clock is legal there and nowhere else).
- **Cache**: key `sha256(method + " " + url + " " + canonical_json(params or {}))`, stored at
  `<cache_dir>/<key[:2]>/<key>.json` as `{"status": int, "headers": {..}, "body": str}`. `cache=True` reads
  a hit without a request; `cache=False` refetches and rewrites. The cache is inside the dataset directory
  (`data/datasets/<name>/cache/`), is excluded from `dataset_hash`, and may be deleted at any time.
- **Backoff**: on `429` and on any `5xx`, wait `min_interval_ms * 2 ** attempt` and retry up to
  `max_retries`, then raise `ProviderError`. A `4xx` other than `429` raises `MalformedResponseError` or
  `ProviderError` at once, with no retry.
- **Proxy**: `proxy` defaults to `os.environ.get(HTTP_PROXY_ENV)`; D4 passes it explicitly and raises
  `ProviderBlockedError` when the served certificate or body identifies `anj.fr`.

### 7.12 Importer and fetcher signatures (D2, D3, D4, D5, composed by D6)

D6 orchestrates the importers and the fetchers in the same wave, blind, so the shape is one shape.
**Every importer and fetcher returns objects in memory and writes no file; D6 alone writes files.**

```python
def import_kalshi(*, client: HttpClient, window_start_ms: int, window_end_ms: int, freeze_ms: int,
                  limit: int | None = None) -> tuple[Market, ...]: ...
def import_manifold(...)  -> tuple[Market, ...]          # same keyword-only signature
def import_polymarket(...) -> tuple[Market, ...]         # same
def import_metaculus(...) -> tuple[Market, ...]          # same; raises NotConfiguredError without a token

def fetch_wikipedia_current_events(*, client: HttpClient, day_start_ms: int) -> tuple[NewsItem, ...]: ...
def fetch_wikipedia_asof(*, client: HttpClient, title: str, asof_day: str,
                         market_id: str) -> tuple[NewsItem, ...]: ...
def fetch_wayback(*, client: HttpClient, day_start_ms: int) -> tuple[NewsItem, ...]: ...
def fetch_gdelt(*, client: HttpClient, day_start_ms: int) -> tuple[NewsItem, ...]: ...
def fetch_comments(*, client: HttpClient, market: Market) -> tuple[NewsItem, ...]: ...

def link_items(items: Sequence[NewsItem], markets: Sequence[Market]) -> tuple[NewsItem, ...]: ...
    # returns copies with match_ids and match_scores_permille set (section 7.6), input untouched
```

A returned `Market` is **unsealed and incomplete by design**: `hardness_tags = ()` (D6 computes them,
section 7.5), `quality` filled from what the provider gave, `fold` unknown, `visible_from_ms` of a returned
`NewsItem` already stamped with the caller's `safety_lag_ms`. An importer raises `ProviderError`,
`MalformedResponseError`, `ProviderBlockedError` or `NotConfiguredError` and never returns a partial market.

L1 needs markets that have **not** resolved, which no importer above returns, so each real-money provider
also exposes:

```python
@dataclass(frozen=True, slots=True)
class OpenMarket:                                        # a Market without an outcome; never enters a dataset
    id: str; provider: str; provider_id: str; url: str; question: str; description: str
    category: str; tags: tuple[str, ...]; wiki_subjects: tuple[str, ...]; currency: str
    created_at_ms: int; close_at_ms: int; interval_min: int
    bars: tuple[Bar, ...]                                # truncated at now_ms, completed bars only
    first_price_bp: int; last_price_bp: int              # as-of, section 5.4
    quality: MarketQuality; fee_schedule_id: str

def list_open_kalshi(*, client: HttpClient, now_ms: int, limit: int | None = None) -> tuple[OpenMarket, ...]: ...
def list_open_manifold(*, client: HttpClient, now_ms: int, limit: int | None = None) -> tuple[OpenMarket, ...]: ...
```

### 7.13 Where the schemas live

The five JSON schemas are **inside the package**, at `src/pmx/schemas/*.json` (owned by C0, section 13),
because `A5` hands `actions.v2.json` to the Claude Code CLI through `--json-schema` at run time and D1's
loader validates every dataset file against them: a path relative to the repository root does not exist in
an installed `pmx`. D1 exposes the one resolver, and no package builds a schema path of its own:

```python
SCHEMA_DIR: Path                                          # pmx.data.schema, = Path(__file__).parent.parent / "schemas"
SCHEMA_FILES = ("market.v2.json", "news.v1.json", "dataset.v1.json", "actions.v2.json", "journal.v2.json")
# amendment C1 added cluster.v1, opportunity.v1, features.v1, model_card.v1; amendment C1b adds
# instrument.v1, cash_event.v1, session_calendar.v1, forecast.v1 (section 17; the tuple is D1's, 17.9);
# amendment C1c adds rule.v1, sensor.v1, workflow.v1 (section 18; applied to the tuple by DS1, 18.8)
def load_schema(name: str) -> dict[str, object]: ...       # cached; raises SchemaError on an unknown name
def schema_path(name: str) -> Path: ...                    # for --json-schema argv
```

U4 adds the packaging line that ships them in a wheel
(`[tool.setuptools.package-data] pmx = ["schemas/*.json", "llm/prompts/*.md"]`); it is a contract issue
against `pyproject.toml`, not a file any other package edits.

### 7.14 The tag taxonomy and the deterministic tagger (amendment C1c, decisions D-S6, D-S8, D-S9, D-S14)

`tags` was a raw dump of provider labels: 201 distinct values over the 287 markets of `y2026`, the most
frequent a Kalshi series ticker seen sixteen times, 58 markets whose tag merely repeated their category
(`docs/REVIEW_2026-09-09_SCALE_TAGS.md`). A field like that cannot group markets for a comparison, and a
comparison is what the cohort of 18.5 is for. So:

**Three facets and a controlled vocabulary** (ruling R265). `src/pmx/lexicons/tags.v1.json` (DS2) ships
the vocabulary as `{"version": "tags.v1", "facets": {"subject": {<value>: {"keywords": [..]}},
"structure": {<value>: {"patterns": [..]}}, "horizon": [..], "builder": [..]}}`; every market carries:

| Facet | Cardinality | Values (the vocabulary starts from what was measured, D-S14, and grows only by a new lexicon version) |
|---|---|---|
| `subject` | one or more, **in tagger precedence order** (the first is the primary subject, the cohort key of 18.5), unique, at most 4 | at least `bitcoin`, `gold-silver`, `gas-prices`, `oil`, `cpi-inflation`, `treasury-yields`, `equity-index`, `single-equity`, `precipitation`, `temperature`, `elections-us`, `us-executive`, `armed-conflict`, `ai-models`, `spaceflight`, `net-worth`, `platform-meta`, plus D-S6's `central-bank-rates`, `employment`, `fx-major`, `epidemics`, `storms`, `court-rulings`, and `other` |
| `structure` | exactly one | `threshold-above` (145 Kalshi markets measured), `threshold-below` (15), `count-over-period` (10), `head-to-head` (9), `range-band` (7), `by-date` (7 Kalshi, 12 Manifold), `multi-outcome-leg`, `recurring-series-leg`, `other` |
| `horizon` | exactly one, **derived from the market's life and never from provider text**: `life_ms = close_at_ms - created_at_ms` (the venue's published close, public from listing; never `resolved_at_ms`) | `intraday` (`< MS_PER_DAY`), `week` (`< 7 d`), `month` (`< 31 d`), `quarter` (`< 183 d`), `year-plus` (the rest); the boundaries are defaults the first tagged build reports against |
| `builder` (a label, not a facet a market must carry) | zero or more | `forecastable_from_public_models` (weather series, D-R13) |

`tags` **stays**, as the sorted unique union of the market's facet values and builder labels (so
`Memory.prior(tag=...)`, `PerMarket.tags`, `per_tag` of a claim and every consumer of `tags` keep working
on values that mean something), and the builder refuses a `tags` value outside the vocabulary
(`SchemaError`). The raw provider strings move, verbatim, to **`provider_labels`** (same pattern as
`tags`, `<= 16`, sorted, unique): never a cohort key, never displayed as a tag, kept so a reviewer can see
what the provider said. `market.v2.json` carries `provider_labels`, `subject`, `structure` and `horizon`
as **optional** fields so that a file written before the taxonomy still loads; the loader requires all four
on every market of a dataset whose manifest carries the `taxonomy` block below, and refuses a facet value
outside the vocabulary that block names. `market_listed` (9.2) carries the four **and `cohort_id`** beside
`tags` (ruling R288), so the projection reads the cohort of a market off the journal instead of
re-implementing `pmx.cohorts.list_cohorts`'s keying rule, exclusions included, in a second place.

**The tagger is deterministic and auditable, never a model call** (ruling R267; `pmx.data.taxonomy`, DS2):

```python
def tag_market(market: Market, *, lexicon: TagLexicon, series_facets: Mapping[str, SeriesFacets]) -> Facets: ...
    # Facets(subject: tuple[str, ...], structure: str, horizon: str, labels: tuple[str, ...], source: str)
```

in this order and no other: (1) the sealed provider mapping `src/pmx/lexicons/kalshi_series_facets.v1.json`
(DS2), a series ticker (the part of a Kalshi ticker before the first dash, the key of ruling R170's map)
to its subjects and its structure, which wins outright when the series is present (`source =
"series"`; the tagger's `subject` facet and the linker's `wiki_subjects` of 7.6 are **different
vocabularies with different purposes**, so `kalshi_series_facets.v1.json` never supersedes D2's
`kalshi_series_subjects.v1.json`, and DS2 derives the former from the latter where the two agree and
records the derivation in the file, ruling R295); (2) the keyword rules of the vocabulary over the lowercase alphabetic tokens of `question`
(the stop list of 7.6 applied), each subject's `keywords` matched as whole tokens and the subjects
ordered by the vocabulary's order, then the `structure` decided by the **first** of the vocabulary's
ordered regular expressions that matches the question (`source = "keywords"`); (3) `other` for a facet
nothing decided, counted in the manifest (`source = "other"`). `horizon` is always derived. No network, no
randomness, no wall clock; the two lexicon files are **copied into the dataset** at
`data/datasets/<name>/taxonomy/tags.v1.json` and `taxonomy/kalshi_series_facets.v1.json`, inside the walk
of 4.3 and therefore inside `dataset_hash`, so a tag that moved between two rebuilds moves the hash and
not a claim. Byte-identical across two runs is a DS2 test. A self-referential Manifold market ("Will this
market be above 50 percent when it closes?") is `subject = ("platform-meta",)` by keyword rule, and the
provider's `nonpredictive` label is reconciled into the same subject (measured: 7 self-referential, 8
`nonpredictive`, not the same set, D-S14), so `platform-meta` is one audited subject and never a silent
`other`; a `platform-meta` market belongs to no cohort (18.5).

**Coverage is measured and labelled** (rulings R268 and R273). The manifest's `taxonomy` block (7.8)
records, **per venue** and per facet, the share of markets carrying a value other than `other`
(`coverage_permille`), the number of distinct values, the `other` and `platform-meta` counts, the
cohort size histogram (`1`, `2-4`, `5-9`, `10-29`, `30+`), the number of cohorts and of usable cohorts,
and a label per venue: `taxonomy: "weak"` for a venue whose `subject` coverage is below
`TAXONOMY_COVERAGE_MIN_PERMILLE = 900` (ninety percent, D-S14: a single 95 percent bar is unreachable on
Manifold by construction, whose `other` bucket is expected to be large and is reported rather than hidden)
or whose usable cohorts are fewer than `TAXONOMY_MIN_USABLE_COHORTS = 10`, `"ok"` otherwise. Every
leaderboard row and every chart grouping by a facet or a cohort carries the venue's label in
`LeaderboardRow.labels` (12.10), exactly as `news_links: "weak"` is carried (7.6). **A manual audit of
`TAXONOMY_AUDIT_N = 50` random taggings** per build, drawn with `sample_without_replacement` from the
`dataset.subsample` substream, is stored as `audits/<dataset_hash[:16]>/taxonomy.json`
(outside the walk, keyed by `dataset_hash`, **tracked** beside the linker audit, ruling R296) with the
reviewer's verdicts
(`correct | wrong | unsure` per facet) and the manifest's `taxonomy.audit {path, n, precision_permille}`
reports the precision; gate G3 performs the review. A tag cannot leak (18.5): it is computed from
`question`, `provider_id`, the series map and the published life, and the tagger reads none of 7.9's fields,
which `tests/test_taxonomy.py` asserts by handing it a market whose `resolution`, `resolved_at_ms`,
`final_price_bp` and bars are poisoned and checking the facets do not move.

---

## 8. The engine

### 8.1 `RunConfig` (`pmx.types`)

```python
@dataclass(frozen=True, slots=True)
class RunConfig:
    seed: int                                  # 0 <= seed < SEED_SPACE
    interval_min: int = 1_440
    t0_ms: int | None = None                   # None: bar_of(min created_at) of the run's markets
    t1_ms: int | None = None                   # None: bar_of(max resolved_at) + interval
    bankroll_cents: int = 100_000
    volume_cap_permille: int = 100             # a market order may take at most 10 percent of the bar's volume
    slippage_bp_per_pct: int = 10              # 10 bp per percent of bar volume taken
    ruin_floor_cents: int = 1_000              # equity at or below this freezes the agent (decision D-5)
    bars_window: int = 90                      # completed bars shown per market (168 for hourly runs)
    trades_window: int = 200                   # trades shown when research "history" is granted
    news_per_market: int = 20
    news_global: int = 50
    hive_lessons: int = 20
    hive_forecasts: int = 200                  # settled forecasts of other agents in a view, <= HIVE_FORECASTS_MAX
    markets_per_obs_max: int = 200             # <= MARKETS_PER_OBS_MAX; the actions schema caps the reply at 200
    research_budget_units: int = 10            # per agent per run, unless overridden below
    research_budget_by_agent: tuple[tuple[str, int], ...] = ()   # sorted by agent_id, overrides the scalar
    amnesic: bool = False                      # memory reset at run start and never persisted
    no_hive: bool = False                      # hive reads return empty views; writes are still journaled
    live_coop: bool = False                    # stacker may read the previous bar's forecasts (off by default)
    memory_frozen: bool = False                # claims only: learn() may not write
    memory_from_run_id: str | None = None      # load every agent's memory snapshot from that run's manifest
    hive_from_run_id: str | None = None        # load the hive snapshot from that run's manifest
    contamination_hash: str | None = None      # sha256 of contamination.json when an LLM row is scored
    fold: str = "all"                          # "train" | "validation" | "sealed" | "all"
    market_ids_hash: str = ""                  # sha256(canonical_json(sorted market ids of the run))
    liquidity: str = "historical"              # one of LIQUIDITY_MODELS (section 16.1)
    liquidity_params_hash: str = ""            # sha256(canonical_json(params)) of that model, "" when none
    horizons_bars: tuple[int, ...] = ()        # amendment C1b, 17.5: () means default_horizons_bars(interval_min)
    kinds: tuple[str, ...] = ()                # amendment C1b, 17.2: the kinds the run carries, () meaning every kind
    sensor_catalogue_hash: str = ""            # amendment C1c, 18.1, ruling R231: CATALOGUE_HASH of the sensor catalogue
                                               # the run must read; "" means the shipped one; a non-empty value that
                                               # differs from it is InvalidConfigError (the liquidity_params_hash pattern)
    def to_dict(self) -> dict[str, object]: ...
        # every value is an int, a bool, a str, None, or a list of [str, int] pairs; canonical_json accepts it
```

`fold` and `market_ids_hash` are in the config, and therefore in `config_hash` and in the run id, because
a generation runs the same population, the same seed and the same config on the training and on the
validation fold: without them the two runs share a run id, overwrite each other's journal, and a validation
number can be presented as a training number with nothing in the artefacts to tell them apart.
`market_ids_hash` is set by the caller with `pmx.types.market_set_hash(ids)` (a different name from the
field, so nothing shadows anything); `run_backtest` recomputes it
over the markets it was handed and raises `InvalidConfigError` on an empty or mismatching value.

`liquidity` and `liquidity_params_hash` are amendment C1's two fields (section 16.1, ruling R112) and they
are in the config for exactly ruling R8's reason: two runs that differ only in the tape they had to trade
against must not share a run id, a directory, a journal or a claim. `run_backtest` raises
`InvalidConfigError` when the `LiquidityModel` it is handed reports a `model_id` or a `params_hash` that
disagrees with these two names, so a journal can never claim a liquidity it did not run under.

`horizons_bars` and `kinds` are amendment C1b's two fields (sections 17.2 and 17.5, rulings R144 and
R157) and are in the config for the same reason: the horizons a run scores and the kinds it carries
change every continuous score and every row, so two runs that differ in them must not share a run id.
`RunConfig.__post_init__` resolves `()` to `default_horizons_bars(interval_min)` before `to_dict()` and
therefore before hashing, so a config that spells the default and one that omits it are one run (ruling
R201; the runner reads the resolved field and resolves nothing of its own).

`memory_from_run_id` and `hive_from_run_id` are in the config for the same reason: memory carried between
runs is a channel into an observation, so it must move the run id. The runner loads the named run's
manifest, computes `memory_hash = sha256(canonical_json(manifest.memory_snapshots))`, journals both in
`run_started` with the source run's `t1_ms`, and raises `LeakError` when that `t1_ms > t0_ms` of the run
being started (a snapshot taken from a run that covered the validation or the sealed months would inject
resolved outcomes into `calibrator`'s bin table, and no as-of filter would see it). Amendment C1c adds
two refusals the instant guard cannot make (5.6, ruling R291): `ShowcaseDatasetError` when the named run
ran on a `purpose: "showcase"` dataset, and `LeakError` when the named run's `dataset_hash` differs from
this run's. Memory travels **forward inside one dataset** and nowhere else; a live run seeded from a
backtest is a mechanism the live wave must write into this contract, not a flag.

Caps the config may not exceed (`pmx.types`, mirrored in the schemas): `BARS_WINDOW_MAX = 720`,
`TRADES_WINDOW_MAX = 1_000`, `NEWS_PER_MARKET_MAX = 50`, `NEWS_GLOBAL_MAX = 200`, `HIVE_LESSONS_MAX =
50`, `HIVE_FORECASTS_MAX = 2_000`, `MARKETS_PER_OBS_MAX = 200`, `NOTES_MAX_CHARS = 500`,
`LESSON_MAX_CHARS = 300`, `LESSONS_PER_BAR_MAX = 5`, `RATIONALE_MAX_CHARS = 2_000`,
`OBSERVATION_MAX_BYTES = 8_388_608` (8 MiB of canonical JSON; the builder raises
`ObservationTooLargeError` rather than truncating silently). A `wiki_asof` grant carries at most
`news_per_market` revisions (most recent first, `visible_from_ms` filtered, ruling R210), so a granted request
cannot push an observation over the cap.

Research costs are a table, not a guess, so E1 (which grants) and E5 (which journals) agree:

```python
RESEARCH_UNIT_COST = {"news": 1, "history": 2, "wiki_asof": 3}     # pmx.types
RESEARCH_PENALTY_UNITS = 5                                          # section 12.6
```

`research_spent.units` is `RESEARCH_UNIT_COST[kind]`, and a request whose cost exceeds the remaining
budget is journaled with `granted: false` and costs nothing.

### 8.2 The bar phase order

For every bar `t` of the calendar, in this order, with this purity:

| # | Phase | What happens | Pure? | Events |
|---|---|---|---|---|
| 1 | `open` | list newly listed markets; compute the open, tradable, settling and closing sets; record each market's metadata once and each open market's bar prices; expire limit orders whose `expires_at_ms <= t` or whose market is no longer tradable | yes | `bar_opened`, `market_listed`, `market_priced`, `order_expired` |
| 2 | `observe` | build one `Observation` per non-ruined agent with the as-of filter (section 5.4) **narrowed to the agent's sensor set** (`build_observation(..., sensors=genome.sensors)`, section 18.1, ruling R230; the sensor blocks of 18.1 are computed here from the same views); grant research requested at `t - interval` | yes | `observation_built` (carrying `sensors`, ruling R231) |
| 3 | `decide` | scripted agents: `observe(obs)` then `decide()` (a workflow genome runs its steps in topological order, section 18.4); LLM agents: one gateway call per agent covering every open market, reply handed to the agent, then `decide()`; validate every `Actions` (a `propose_rule` included, section 8.4); record a forecast for every open market (carried when missing); write LLM lessons to memory; hand every order-producing action to `Execution.place` (section 8.6), which **queues** it for the next bar and reserves nothing | **impure for LLM agents only** (the gateway) | `reply_received`, `action_received`, `action_rejected`, `forecast_recorded`, `research_spent`, `memory_written` (lessons), `rule_proposed`, `workflow_step_executed` (amendment C1c, section 18) |
| 4 | `execute` | drain the queue `place` accepted at the instrument's previous bar (`t - interval_ms` on a `continuous` calendar, Friday's last bar on a Monday, section 17.2, ruling R192), agents in `agent_id` order, intents in submission order: place orders, fill market orders at bar `t`'s open through the run's `LiquidityModel` (section 16.1), try resting limit orders against bar `t`'s range, charge fees, reserve and release cash | yes | `order_placed`, `order_rejected`, `filled`, `fee_charged` |
| 5 | `settle` | for each market with `settles(m, t)`, in market order: `Execution.settle` pays every position and cancels every resting order on it and returns the per-agent cash deltas; the runner, which holds the forecast history and `pmx.scoring`, emits the two scored events. Then, for each continuous instrument in canonical order (amendment C1b, section 17.3): `Execution.apply_cash_events` applies the cash events whose application bar is `t` (section 17.3, ruling R175) and, at `last_bar(i)`, `Execution.force_flat` closes every position at the bar's close; the runner emits `forecast_resolved` for every horizon that resolves at `t` and `instrument_closed` at `last_bar(i)` | yes | `settled`, `settlement_applied` (both from the runner), `order_expired` (reason `settled`, from execution); `cash_event_applied`, event-fill `order_placed`, `filled`, `fee_charged`, `order_expired` (reasons `corporate_action`, `roll`, `delisted`, from execution); `forecast_resolved`, `instrument_closed` (from the runner) |
| 6 | `learn` | for each settled market and each agent that forecast or held it, in agent order: `agent.learn(ResolutionEvent)`; memory writes journaled | yes | `memory_written` |
| 7 | `hive` | in this order: one `forecast` entry per `forecast_recorded` of this bar in agent order (stamped `bar_of(resolved_at_ms) + interval_ms`, so the index releases it after settlement without a second write), then one `resolution` entry per market that settled this bar in market order, then a `reputation` entry per affected `(agent, category)` in agent then category order, then a `lesson` entry per lesson and note written this bar (visible from `t + interval_ms`) | yes | `hive_written` |
| 8 | `close` | mark every agent at `mark_price_bp`, the close of bar `t` itself (section 8.7; `mark_value_cents` of 17.1, signed, on a continuous instrument), update peak and drawdown, freeze ruined agents and expire their resting orders | yes | `equity_marked`, `agent_ruined`, `order_expired` (reason `ruined`), `bar_closed` |

**The phase order itself is unchanged by amendment C1, and `execute` stays after `observe`** (section
16.2, ruling R108). `PHASE_ORDER` (section 9.1), the `phase` constant of every event of section 9.2 and
the order `verify_journal` compares against are all exactly what they were: the only thing the decision
latency rule moves is **what the execute phase drains**, which is now the queue of bar `t - interval_ms`
rather than the decisions of bar `t`. Draining the queue before the observe phase would look more
physical and is forbidden: a fill at bar `t`'s open lands in the agent's cash and in `avg_cost_bp`, so an
observation built after it would carry the price of a bar that has not completed, which is exactly the
leak section 5.4 exists to prevent. An agent therefore learns of its fill in the observation of
`t + interval_ms`, by which time bar `t` is completed and its open is public. Two consequences are
stated rather than defaulted away: `target` is the safe idiom under latency, because a target repeated
while a fill is in flight is a no-op once the fill lands, whereas a `limit` repeated on consecutive bars
rests **twice**; and an action decided on the run's last bar (`t + interval_ms == t1_ms`) has no execute
phase to drain it, so it is dropped, which E5's test states as "no `order_placed` carries a
`decided_at_ms` equal to its instrument's last actionable bar or later" (`t1_ms - interval_ms` on a
`continuous` calendar, ruling R192).

**A ruined agent is skipped in `observe` and `decide` but never in the forecast record.** The runner
still emits `forecast_recorded(carried=true)` for every open market at every bar of the rest of the run,
with the agent's last stated probability on that market, or `500_000` for a market listed after the ruin
that it never observed. Without that rule a ruined agent's scored bar set would be a subset chosen by when
it died: its `n_markets` would shrink, dying would become a way to drop the markets it was losing on, and
section 12.1's per-agent Brier would no longer be computed on the same bars as the single
`settled.market_brier_tw_micro` the projection has to use. E5's test asserts that
`settlement_applied.n_forecast_bars` is equal across every agent of the roster, for every market.

`learn` is pure even for LLM agents: an LLM agent's `learn()` queues the settled market's post-mortem
request, and the lesson **text** is produced by the next bar's single gateway call (the prompt lists
"markets resolved since your last call"), arriving in the `lessons` field of the reply and journaled as
`memory_written` in `decide`. One call per agent per bar is therefore a structural fact (section 11.3).

### 8.3 `Observation` (`pmx.types`, `obs_version = "obs.v2"`)

```python
@dataclass(frozen=True, slots=True)
class Observation:
    obs_version: str                       # "obs.v2"
    agent_id: str
    now_ms: int
    interval_min: int
    markets: tuple[MarketView, ...]        # open markets, sorted by market_id, <= markets_per_obs_max
    news: tuple[NewsView, ...]             # global digest, <= news_global, ranked (section 3)
    portfolio: PortfolioView
    memory: MemoryView                     # the agent's own memory, read-only
    hive: HiveView                         # empty when no_hive
    research: ResearchView
    limits: Limits
    sensors: tuple[str, ...] = ()          # amendment C1c, 18.1, ruling R231: the RESOLVED sensor set, sorted; the full
                                           # SENSOR_NAMES when the genome bought everything, so a catalogue change is
                                           # visible on the face of every observation; () only on a view built before
                                           # the field existed. A field a sensor set did not buy is ABSENT from this
                                           # object and from to_dict(), never zeroed (ruling R230)
    def to_dict(self) -> dict[str, object]: ...     # canonical-json-able, no float

@dataclass(frozen=True, slots=True)
class MarketView:
    market_id: str; provider: str; url: str; question: str; description: str   # description <= 1000 chars
    category: str; tags: tuple[str, ...]; currency: str
    created_at_ms: int; close_at_ms: int; tradable: bool   # close_at_ms is 0 and tradable is open(i, t) on a
                                           # continuous instrument (ruling R181)
    bars: tuple[Bar, ...]                  # completed bars, oldest first, <= bars_window; () on the first bar;
                                           # one Bar type for every kind, _bp fields in ticks (ruling R173)
    first_price_bp: int                    # the market's opening quote; public from the first bar
    last_price_bp: int                     # close of the last completed bar, else first_price_bp (section 5.4)
    best_bid_bp: int | None; best_ask_bp: int | None    # from the last completed bar, else None
    volume_milli_7d: int; volume_milli_to_date: int; n_trades_to_date: int
    trades: tuple[Trade, ...]              # empty unless research "history" was granted for this market
    news: tuple[NewsView, ...]             # items linked to this market, <= news_per_market, ranked
    position: PositionView
    fee_schedule_id: str
    # Amendment C1b, ruling R188: eight defaulted fields, D1's (gate G2), filled by E1. to_dict() renders
    # them always, so a binary observation gains eight keys at their defaults; no run of 2026-09-08 exists
    # whose bytes that could move.
    kind: str = "binary"                   # one of INSTRUMENT_KINDS
    tick_size_micro: int = 100
    point_value_micro: int = 1_000_000
    session_calendar_id: str = "continuous"
    hours_to_next_bar: int = 0             # (Calendar.session_next_bar(i, now_ms) - now_ms) // MS_PER_HOUR from
                                           # the sealed calendar (public, the venue's rule; R208); 0 on a binary
    underlying_id: str | None = None       # a perp's spot twin when the run carries it (17.7 basis)
    twins: tuple[str, ...] = ()            # the instrument's twins the run carries (17.7 pairs)
    cash_events: tuple[CashEventView, ...] = ()   # APPLIED data events, oldest first, <= CASH_EVENTS_VIEW_MAX
                                           # (ruling R183); () on a binary

CASH_EVENTS_VIEW_MAX = 30
# The view caps stated in prose here and in 8.4 are pmx.types constants the builder imports (ruling R208):
NEWS_VIEW_TEXT_CHARS = 600; DESCRIPTION_VIEW_CHARS = 1_000; HIVE_RESOLUTIONS_VIEW_MAX = 200
MEMORY_NOTES_VIEW_MAX = 20; RESEARCH_NEWS_MULTIPLIER = 3

@dataclass(frozen=True, slots=True)
class CashEventView:                       # amendment C1b, ruling R183: one applied data cash event
    kind: str                              # funding | dividend | split | roll (never an engine kind)
    t_ms: int                              # the record's t_ms
    applied_at_ms: int                     # applies_at(e) of 17.3; a completed bar at now_ms
    detail: Mapping[str, int | str]        # the record's detail verbatim

@dataclass(frozen=True, slots=True)
class NewsView:
    news_id: str; source: str; kind: str; published_at_ms: int; headline: str
    text: str                              # <= 600 chars in a view (the dataset keeps 4000)
    section: str | None; url: str; match_score_permille: int

@dataclass(frozen=True, slots=True)
class PositionView:
    position: int                          # signed contracts, negative = NO held; on a continuous instrument
                                           # signed milli-units, negative = short (rulings R148, R154)
    avg_cost_bp: int                       # volume-weighted entry price of the open leg, 0 when flat
    unrealised_cents: int                  # marked to last_price_bp
    open_orders: tuple[OpenOrderView, ...] # order_id, side, price_bp, remaining_size, expires_at_ms

@dataclass(frozen=True, slots=True)
class PortfolioView:
    cash_cents: int; reserved_cents: int; equity_cents: int; fees_paid_cents: int
    # cash_cents is SIGNED (a debit cash event may leave a debit balance, ruling R179) and so is equity_cents
    # (a short is a liability, ruling R154); drawdown_bp has no floor once equity can be negative (R180)
    peak_equity_cents: int; drawdown_bp: int; n_open_positions: int; n_open_orders: int
    research_units_remaining: int

@dataclass(frozen=True, slots=True)
class MemoryView:                          # section 10.3; a snapshot, never the live object
    calibration: tuple[CalibrationBinView, ...]      # (category, horizon_bucket, bin, n, n_yes, n_yes_x2 = 0)
                                                     # n_yes_x2 is 2 * n_yes on a binary slice; on a continuous
                                                     # slice n_yes = n_yes_x2 // 2 and every ratio reads n_yes_x2
                                                     # over 2 * n (17.5, ruling R194); to_dict() renders
                                                     # n_yes_x2 always (ruling R217)
    priors: tuple[PriorView, ...]                    # (category or "tag:<tag>", n, n_yes)
    features: tuple[FeatureStatView, ...]            # (family, key, n, sum_milli, sum_sq_milli)
    lessons: tuple[LessonView, ...]                  # (written_at_ms, text, market_ids)
    notes: tuple[NoteView, ...]                      # (written_at_ms, market_id | None, text), last 20

@dataclass(frozen=True, slots=True)
class HiveView:
    lessons: tuple[HiveLessonView, ...]              # ranked, <= hive_lessons (entry_id, author_id, author_skill_micro, text, market_ids, visible_from_ms)
    reputations: tuple[ReputationView, ...]          # (agent_id, category, n, skill_micro, pnl_cents) visible as of now
    resolutions: tuple[ResolutionView, ...]          # (market_id, outcome, life_mean_price_bp, resolved_at_ms), last 200
    forecasts: tuple[ForecastView, ...]              # (agent_id, market_id, bar_ms, prob_ppm) of SETTLED markets only, <= hive_forecasts
    prev_bar_forecasts: tuple[ForecastView, ...]     # forecasts of other agents at the instrument's previous bar (R211); EMPTY unless live_coop
    insights: tuple[InsightView, ...] = ()           # amendment C1c, 18.2, ruling R239: the promoted, undemoted rules
                                                     # whose condition FIRES at now_ms on one of the agent's open markets,
                                                     # <= limits.hive_insights, ranked (-lower_bp, rule_id); gated by the
                                                     # hive_insights sensor; reputations by hive_reputation (ruling R233)

@dataclass(frozen=True, slots=True)
class InsightView:                                   # amendment C1c, 18.2: one firing insight on one market
    rule_id: str; market_id: str
    claim_kind: str; direction: int                  # RuleClaim.kind and .direction (18.2)
    lift_bp: int; lower_bp: int; upper_bp: int       # the replicate-fold interval of the rule's effect, in bp
    live_support: int; live_lower_bp: int            # the live record so far (rows after fit_t1_ms)
    author_id: str; author_skill_micro: int          # the author's reputation in the rule's dominant category as of now_ms

@dataclass(frozen=True, slots=True)
class ResearchView:
    units_remaining: int
    granted: tuple[ResearchGrant, ...]               # kind, market_id, granted_at_ms, payload (NewsView list | Trade list | background NewsView)

@dataclass(frozen=True, slots=True)
class Limits:
    bars_window: int; news_per_market: int; news_global: int; hive_lessons: int; hive_forecasts: int
    markets_per_obs_max: int
    notes_max_chars: int; lessons_per_bar_max: int; lesson_max_chars: int; research_units_total: int
    hive_insights: int = 50                          # HIVE_INSIGHTS_VIEW_MAX (18.2, ruling R239)
```

`prev_bar_forecasts` is named for what it is. The earlier spelling (`live_forecasts`, "same-bar forecasts")
was impossible: every observation is built in the `observe` phase, before any agent decides, so no same-bar
forecast exists, and a view that read one would depend on the order agents are served in and would break
byte determinism. Normatively: every entry satisfies `bar_ms ==` the instrument's previous bar (`now_ms - interval_ms` on a
`continuous` calendar, rulings R192 and R211), the tuple is empty
when `live_coop` is false, and `Hive.view` is a pure function of `(now_ms, agent_id, market_ids, limits,
live_coop)`. A3's test asserts both.

**More than `markets_per_obs_max` open markets.** The reply schema caps `markets` at 200 items and section
8.4 allows at most one action per open market, so a bar with more open markets than the cap would make
every LLM reply `schema_invalid`. When more are open, the observation carries the **first
`markets_per_obs_max` by `market_id` ascending among the tradable ones, then by `market_id` ascending among
the rest**; the markets that did not fit are still forecast-carried by the runner (section 8.2) and still
scored, they are simply not addressable this bar. The rule is deterministic, so E1, E5 and A5 agree and the
actions cap is never reachable.

**Never in an observation**: any field of section 7.9, a bar count, a bar index relative to the end,
`resolved_at_ms`, `delisted_at_ms`, `last_bar(i)`, the run's `t1_ms`, the number of bars remaining, a
`CashEvent` whose application bar has not completed, other agents' forecasts on open markets (unless
`live_coop`, and then only the previous bar's).

**The clock test (E1) is structural, not an integer scan.** A scan cannot pass on legal data: section 7.2
allows `close_at_ms == resolved_at_ms` (the Manifold and Kalshi normal case, and the demo pack's own
Brexit market), `close_at_ms` is required in every `MarketView`, and `Limits` carries `bars_window = 90`
and `news_per_market = 20`, which collide with the bar count of any 90-bar or 20-bar market. The test is
therefore, literally:

1. the recursive **key set** of `leak_scan_payload(Observation.to_dict())`, the payload with
   `HiveView.resolutions` (a settled market's published resolution) and `MarketView.cash_events` (an applied
   event's verbatim detail, ruling R183) set aside, contains none of `resolved_at_ms`, `n_bars`,
   `bars_remaining`, `bar_index`, `t1_ms`, `resolution`, `resolution_source`, `hardness_tags`, `quality`,
   `fold`, `final_price_bp`, `delisted_at_ms`, `last_bar`, nor any structural name of the records 7.9 bans
   (`cluster_id`, `constraint_id`, `reasons`, `asof`, `score_permille`, `resolution_span_ms`,
   `opportunity_id`, `detector_id`, `evidence`, `window`, `duration_bars`, `size_ppm`, `size_net_bp`,
   `payoff_cents`, `tradable_for_money`, `detail`); `kind`, `source`, `currency` and `market_ids` are legal
   keys of legal views and are covered by the poisoned-record test, not by the key scan (ruling R209);
2. for a market whose total bar count is deliberately `bars_window` and again `bars_window + 7`,
   `len(view.bars) == min(bars_window, completed bars so far)`, so a length that leaked the end differs;
3. `view.last_price_bp == market.bars[k].close_bp` for the last completed bar `k`, and
   `view.last_price_bp == market.first_price_bp` on the market's first bar;
4. `canonical_json(obs.to_dict())` contains none of the injected poisoned-future strings (section 7.9).

E1 also owns the two literal signatures the runner calls, so E1, E2 and E5 can be written blind of each
other in the same wave:

```python
@dataclass(frozen=True, slots=True)
class BarSlice:
    t_ms: int
    open_ids: tuple[str, ...]; tradable_ids: tuple[str, ...]
    settling_ids: tuple[str, ...]; listed_ids: tuple[str, ...]   # listed_ids: newly listed this bar
    closing_ids: tuple[str, ...] = ()      # amendment C1b, ruling R187: the instruments with closes(i, t)

class Calendar:
    def __init__(self, dataset: Dataset, config: RunConfig, *,
                 calendars: Mapping[str, SessionCalendar] | None = None) -> None: ...
        # None reads Dataset.calendar(id) for the ids the run's instruments name, else the synthesised
        # continuous calendar; the keyword is an override (ruling R208)
    @property
    def t0_ms(self) -> int: ...
    @property
    def t1_ms(self) -> int: ...
    def bars(self) -> Iterator[BarSlice]: ...            # ascending, the union of the run's instruments' bars
                                                         # (17.2, ruling R187); every grid point on a binary run
    def last_bar(self, market_id: str) -> int: ...       # last_bar(i) of 17.2, inside [t0_ms, t1_ms)
    def next_bar(self, market_id: str, t_ms: int) -> int | None: ...   # the instrument's next bar after t_ms
    def prev_bar(self, market_id: str, t_ms: int) -> int | None: ...   # its last bar before t_ms, in the run
        # The three lookups are E1's one implementation (ruling R187): the queue drain of 17.2, decided_at_ms
        # (R192), applies_at (R175) and the forced flat read them and compute nothing of their own. The three
        # are the BarLookups protocol applies_at takes (ruling R204), declared in pmx.engine.calendar beside
        # its one body; Calendar satisfies it by shape.
    def session_next_bar(self, market_id: str, t_ms: int) -> int | None: ...
        # The venue's next bar from the sealed calendar, UNCLAMPED by the run window: the one route to
        # MarketView.hours_to_next_bar, because next_bar is clamped and would announce last_bar(i) (R208)

def build_observation(*, agent_id: str, now_ms: int, config: RunConfig, markets: Sequence[Market],
                      positions: Mapping[str, PositionView], portfolio: PortfolioView,
                      memory: Memory | None, hive: Hive | None, news: Sequence[NewsItem],
                      grants: Sequence[ResearchGrant],
                      calendar: Calendar | None = None,
                      sensors: Iterable[str] | None = None) -> Observation: ...
    # calendar is keyword-only like the rest and a run carrying a continuous kind passes it (ruling R208):
    # tradable = open(i, t), hours_to_next_bar and cash_events are lookups only the calendar can answer
    # sensors is the agent's sensor set (amendment C1c, 18.1, ruling R230): None means every sensor and is
    # byte-identical to the builder without the keyword; a set is applied by SUBTRACTION over what the as-of
    # filters produced, so it can only narrow; an unbought field is absent from the view and from to_dict()
    # and reading it raises SensorAbsentError (13.1); an unknown name is InvalidConfigError. The runner passes
    # genome.sensors. resolve_sensor_set, unsensed_view_fields, SENSOR_VIEW_FIELDS (E1) are the hook's names;
    # the catalogue's reach per sensor is 18.1's table, which SENSOR_VIEW_FIELDS reads from pmx.sensors.catalogue
    # once S1 lands it (the seven rows E1 shipped are the catalogue's rows for the data a dataset carries today)
def render_observation_json(obs: Observation) -> str: ...        # canonical_json, for observations/ dumps
```

### 8.4 `Actions` (`pmx.types`, `actions.v2.json`)

```python
@dataclass(frozen=True, slots=True)
class MarketAction:
    market_id: str
    prob_ppm: int                          # required, 0..1_000_000
    kind: str                              # "hold" | "target" | "limit" | "abstain"
    target_position: int | None            # kind == "target": desired signed position in contracts (milli-units on a continuous instrument, 17.1)
    side: str | None                       # kind == "limit": "buy" | "sell" (of YES; of the instrument otherwise)
    price_bp: int | None                   # kind == "limit": 1..9999 on a binary, 1..PRICE_TICKS_MAX ticks otherwise
    size: int | None                       # kind == "limit": >= 1 (milli-units on a continuous instrument)
    ttl_bars: int | None                   # kind == "limit": 1..TTL_BARS_MAX (= 90)

@dataclass(frozen=True, slots=True)
class ResearchRequest:
    kind: str                              # "news" (deeper digest, 3x caps) | "history" (trades_window trades) | "wiki_asof" (background article: at most news_per_market revisions, most recent first, visible_from_ms filtered, R210)
    market_id: str | None                  # required for "history" and "wiki_asof"

@dataclass(frozen=True, slots=True)
class Lesson:
    text: str                              # 1..LESSON_MAX_CHARS
    market_ids: tuple[str, ...]            # evidence, <= 8

@dataclass(frozen=True, slots=True)
class Actions:
    actions_version: str                   # "actions.v2"
    markets: tuple[MarketAction, ...]      # one per open market at most, sorted by market_id after validation
    research: ResearchRequest | None
    notes: str                             # <= NOTES_MAX_CHARS, "" allowed
    lessons: tuple[Lesson, ...]            # <= LESSONS_PER_BAR_MAX; scripted agents send ()
    rationale: str | None                  # LLM only; goes to llm_trace.jsonl, never to the journal
    horizon_forecasts: tuple[HorizonForecast, ...] = ()   # amendment C1b, 17.5: continuous instruments only
    propose_rule: RuleProposal | None = None    # amendment C1c, 18.2, ruling R237: at most one per agent per bar

@dataclass(frozen=True, slots=True)
class RuleProposal:                        # amendment C1c, 18.2: a Rule minus what the engine stamps
    scope: RuleScope; condition: tuple[Predicate, ...]; claim: RuleClaim; horizon_bars: int; min_support: int
    # The runner builds Rule(author_kind="agent", author_id=agent_id, born_at_ms=now_ms, family_id=None, ...)
    # through rule_from_dict, journals it as rule_proposed (9.2) and refuses a bad one as
    # action_rejected(scope="rule", reason="bad_rule"); actions.v2.json carries it as an optional property.
```

`horizon_forecasts` (ruling R157) carries one `HorizonForecast(market_id, horizon_bars,
up_probability_ppm, quantiles_ticks)` per `(market_id, horizon_bars)` of the run's `horizons_bars` for
the open continuous instruments; a missing pair is carried (the previous statement, else the random
walk), **except the shortest horizon of a market the agent addressed** (ruling R184): when
`horizon_forecasts` has no pair for `(market_id, shortest horizon)` and a `MarketAction` on that market
exists, the runner synthesises the pair from `MarketAction.prob_ppm` with `quantiles_ticks = None`, so a
family that states only `prob_ppm` states a direction. `prob_ppm` of a continuous `MarketAction` is the
up-probability at the shortest declared horizon, and a pair that **is** present for the shortest horizon
must equal it, else `action_rejected(bad_prob)`. `actions.v2.json` carries the optional top-level array.

Semantics:

- `hold`: keep the current position, cancel nothing. **A `hold` never produces an order and never
  produces an `order_placed` event**, whatever the agent's stated probability. `abstain`: explicit
  no-position: the engine closes any open position on that market with a market order, queued at this bar
  and filled at the open of the next one (amendment C1, section 16.2), and
  records `kind = abstain` (abstention is a strategy and is scored as one); when the position is already
  `0` it produces no order either. `target`: the engine sends a market order for
  `target_position - position` contracts, and **a `target` whose `target_position` equals the current
  position produces no order and no event** (never a size-zero order). `limit`: one resting order.
- **One action per market per bar.** A second `MarketAction` on the same `market_id` in one bar is
  `action_rejected(duplicate)` whatever its `kind`, and the **first occurrence in submission order wins**,
  including its `prob_ppm`. The reply schema cannot express the constraint (an array has no key), so the
  runner enforces it and the schema's description states it.
- A missing market keeps its previous forecast (`forecast_recorded.carried = true`, default `500_000`
  at the first bar the agent sees the market) and is treated as `hold`.
- An action on a market that is not open is `action_rejected(unknown_market)`; on an open but not
  tradable market the forecast is recorded and any order is `order_rejected(not_tradable)`.
- A `ResearchRequest` costs `RESEARCH_UNIT_COST[kind]` units (section 8.1) and is granted at the **next**
  bar; a request that would exceed the agent's remaining budget is `research_spent(granted=false)` and
  costs nothing. A request of a kind whose sensor is not in the agent's diet (`history` needs
  `microstructure`, `news` needs `wiki_daily`, `wiki_asof` needs `wiki_asof`; section 18.1, ruling R233) is
  `action_rejected(bad_research)` and costs nothing: the sensor gates whether the request may be made, the
  research budget prices the grant.
- A `propose_rule` (amendment C1c, section 18.2) is validated by `rule_from_dict`; a second one in a bar,
  a predicate outside the vocabulary or a malformed claim is `action_rejected(scope="rule",
  reason="bad_rule")`, a valid one is journaled `rule_proposed` and costs `RULE_PROPOSAL_COST_UNITS = 1`
  sensor unit of that bar (18.1). A proposal on a bar where `diet_cost_units + RULE_PROPOSAL_COST_UNITS`
  exceeds the agent's sensor allowance, or beyond `RULE_PROPOSALS_PER_GENERATION_MAX = 20` for that agent
  in the generation, is `action_rejected(scope="rule", reason="budget_exceeded")` and the genome keeps
  running (rulings R281 and R300). It produces no order and no forecast.

Validation reasons (`pmx.types.RejectReason`, a `StrEnum`): `unknown_market`, `duplicate`, `bad_prob`,
`bad_kind`, `missing_field`, `bad_price`, `bad_size`, `bad_ttl`, `notes_too_long`, `too_many_lessons`,
`lesson_too_long`, `bad_research`, `schema_invalid`, `not_tradable`, `insufficient_cash`, `zero_size`,
`ruined`, `budget_exceeded`, `agent_timeout`, `provider_error`, `malformed_response`, amendment C1b's
`bad_horizon` (a horizon outside `config.horizons_bars`) and `bad_quantiles` (a non-monotone or
wrong-length quantile tuple), and amendment C1c's `bad_rule` (a `propose_rule` that `rule_from_dict`
refuses, section 18.2). `action_rejected.scope` gains `rule`. The notional cap of 17.1 is checked by `Execution` at the execute phase,
where the price is known, and refused as `order_rejected(bad_size)` there and nowhere else (ruling R196). A
structurally
invalid payload (schema failure) becomes a single `action_rejected(scope="actions", schema_invalid)`
plus carried forecasts and `hold` everywhere; a partially invalid payload keeps its valid items
(truncation, never a crash).

### 8.5 Positions and cash

An agent holds at most one leg per market: `position > 0` YES contracts, `position < 0` NO contracts.
An order is expressed on YES (`buy` or `sell`). Netting is mechanical:

- `buy s` with `position = q`: first **closes** `c = min(s, max(0, -q))` NO contracts, receiving
  `proceeds_cents(c, 10_000 - p)`; then **opens** `s - c` YES, paying `cost_cents(s - c, p)`.
- `sell s` with `position = q`: first closes `c = min(s, max(0, q))` YES, receiving
  `proceeds_cents(c, p)`; then opens `s - c` NO, paying `cost_cents(s - c, 10_000 - p)`.
- A fill never takes cash below zero: the opening part is truncated to the largest size whose total outlay
  (the opening cost minus the closing proceeds plus the fee of 8.8) free cash pays (`unfilled_reason = "cash"`),
  which is `floor(free_cash / unit_cost)` on a pure opening fill with no fee (ruling R215; `truncate_for_cash`
  of 16.1 implements it, ruling R130). `free_cash = max(0, cash - reserved)`. Only a debit cash event of
  section 17.3 can leave `cash < 0` (a debit balance, ruling R179), and while it does `free_cash` is `0`.
- A resting limit order reserves the worst-case opening cost of its full size at its limit price
  (`cost_cents(size, p)` for `buy`, `cost_cents(size, 10_000 - p)` for `sell`); the reservation is
  released on fill, expiry or cancellation and re-computed to the remainder on a partial fill; a partial limit
  fill is truncated so that the remainder's reservation stays funded at the maker fee of 8.8, so a remainder
  never rests against an unfunded reservation (ruling R215).
- `avg_cost_bp` of the open leg is volume-weighted on opening fills (`round_half_up`), unchanged on
  closing fills, `0` when flat.

**On a continuous instrument** (amendment C1b, section 17.3, rulings R148 and R154) `position` is
`position_milli`, `size` is `size_milli`, `p` is `price_ticks`, `cost_cents(s, p)` reads
`cash_out_cents(s, p, tick_size_micro, point_value_micro)` and `proceeds_cents(s, p)` reads
`cash_in_cents(...)`, and the NO leg is replaced by the liability model: a `sell` beyond the long opens a
**short** that *receives* `cash_in_cents` at the fill price, a `buy` beyond the short *pays*
`cash_out_cents` to cover, a short is legal only where `short_allowed` holds, and the opening notional of a
short may not exceed the agent's free cash at the fill (`unfilled_reason = "cash"` beyond it). A binary
keeps the NO leg exactly as above: a NO contract is a long in the complement and pays up front.

### 8.6 Fills

A market order of `s` contracts **accepted by `place` at the instrument's previous bar (`t - interval_ms`
on a `continuous` calendar, ruling R192) and drained by `execute_bar` at bar `t`** on market `m` (amendment C1, section 16.2: `place` queues and reserves
nothing, `execute_bar` is where every execute-phase event and every cent comes from):

0. If `not tradable(m, t)` (section 5.3), nothing is placed: `order_rejected(not_tradable)` carrying
   `decided_at_ms = t - interval_ms`, no `order_placed` and no `filled`. This is the one place a deferred
   action expires, and it is also what happens to an action decided on a market's last tradable bar.
   E2's tests assert no `filled` event exists at `bar_of(m.close_at_ms)` or at `bar_of(m.resolved_at_ms)`.
1. `bar = m.bar_at(t)` (always defined, section 5.3). If `bar.volume_milli == 0`: nothing fills,
   `unfilled_reason = "zero_volume"`. **A market with `source == "reconstructed"` is exempt**: its bars
   carry no volume because the source has none (PRD 3.3), not because nothing traded, so the cap of step 2
   is not applied, `taken_pct = 0`, `slippage_bp = 0` and `price_source = "open"` (it read `"vwap"` before
   amendment C1 moved the base price with the latency rule, ruling R113). Without the exemption
   the demo pack, the only committed dataset, would fill nothing and the trading half of waves 2 to 4
   would have no test vehicle at all.
2. `cap_milli = (bar.volume_milli * volume_cap_permille) // 1_000` milli-contracts, shared by every order
   of that (market, bar), market and resting limit alike. **The cap is rationed pro rata, not first come
   first served** (rulings R127 and R141): with `requested` the sum of `size_milli` over the orders drained
   on that market at that bar, order `i` receives `(size_i * cap_milli) // requested`, and the remainder,
   at most one milli-contract per order, goes to the largest fractional parts, ties broken by
   `(-size_milli, side, kind, limit_price_bp)` and then by the canonical order of section 3. Two orders
   that tie on all four keys are the same order in every respect the tape can see, so which of them takes
   the extra milli-contract changes no aggregate, and `Execution` truncates to whole contracts on a binary
   anyway. If
   `requested <= cap_milli` nothing is rationed. An order allocated `0` reports
   `unfilled_reason = "volume_cap"`. `allocate_cap` (section 16.1) is the one implementation.
3. `base = bar.yes_ask_bp` for buys / `bar.yes_bid_bp` for sells when the bar carries quotes
   (`price_source = "quote"`), else `bar.open_bp + hs` for buys / `bar.open_bp - hs` for sells with
   `hs = half_spread_ticks(previous bar, bar, schedule=schedule)`, the half-spread floor of section 17.4
   (amendment C1b, ruling R156; `hs` is `0` on every pair of flat bars, so on the demo pack the base is
   the open exactly as before), clamped into the bar's range, `price_source = "open"`.
4. `taken_pct = (filled_milli * 100) // max(1, bar.volume_milli)`;
   `slippage_bp = slippage_ticks(base, config=config, taken_pct=taken_pct, view=market_view)`, which is
   `slippage_bp_per_pct * taken_pct` on a binary (an absolute number of basis points of the payout, the v2
   rule unchanged) and `round_half_up(base * slippage_bp_per_pct * taken_pct, BP_ONE)` on a continuous kind
   (the same number of basis points, relative to the price, in ticks; ruling R173);
   `fill_price_bp = clamp_price(base + slippage_bp, view=market_view)` for buys,
   `clamp_price(base - slippage_bp, view=market_view)` for sells, where `clamp_price` is `clamp_price_bp` on
   a binary and `max(1, min(PRICE_TICKS_MAX, x))` otherwise (a `clamp_price_bp` left on a continuous path
   would print 6 341 257 ticks as 9 999 and E2's continuous envelope test fails it). The slippage is a function of the order's
   **own allocated** size, which pro-rata rationing makes independent of the arrival order, so the multiset
   of fills over a (market, bar) is invariant under permutation and envelope rule 4 of section 16.1 holds
   exactly (ruling R127). Under the first-come-first-served rule this step used to carry, it did not: two
   buys of 80 and 40 against a cap of 100 produce a different aggregate notional in each of the two orders.
5. Apply section 8.5 netting at `fill_price_bp`, then the cash truncation, which is
   `pmx.engine.liquidity.truncate_for_cash` and not `Execution`'s own arithmetic (ruling R130): it lowers
   `filled_milli` to what cash allows, recomputes `fee_cents` for the smaller size and sets
   `unfilled_reason = "cash"` under the precedence below, so envelope rule 5 holds on the fill the journal
   writes and not merely on the one the model returned.

**Steps 1 to 4 are no longer execution's arithmetic: they are the normative definition of the
`historical` implementation of the `LiquidityModel` protocol** (section 16.1, ruling R113), which lives
in `pmx.engine.liquidity` and is the only module that computes a fill price. `Execution` calls
`model.quote_bar(...)` once per (market, bar) with every order drained there and applies step 5 through
that module's `truncate_for_cash`. Three things moved with the protocol and nothing else did: step 3's
fallback base is the execution bar's **open** rather than its vwap, because an order queued at
`t - interval_ms` executes at the open of `t` (section 16.2), and `price_source` therefore reads `"open"`
where it read `"vwap"`; step 2's cap is rationed pro rata rather than by arrival (rulings R127 and R141);
and step 5's truncation is a declared function of `pmx.engine.liquidity` rather than of `Execution`
(ruling R130).

**`unfilled_reason` is a single enum, so its precedence is fixed**: when more than one truncation applies,
it names the **first that fired** in the order `zero_volume`, `no_cross`, `no_liquidity`, `volume_cap`,
`cash`. A market order truncated by the volume cap in step 2 and then by cash in step 5 reports
`volume_cap`, and E2 and the projection therefore agree on `fill_ratio_ppm` and on the diagnosis.
`no_liquidity` is amendment C1's addition (section 16.1, ruling R111): a `LiquidityModel` may legally
show no depth at a price inside the envelope, and `historical` never returns it.

For a resting limit order (`buy` at `L`): it fills at bar `t` iff `bar.low_bp <= L`, at
`min(L, bar.open_bp)`; `sell` at `L` fills iff `bar.high_bp >= L`, at `max(L, bar.open_bp)`. It does not
cross when the range does not reach `L` (`unfilled_reason = "no_cross"`). This rule is the `historical`
model's too, and it is the reason `quote_bar` receives a `LiquidityOrder` carrying `kind`,
`limit_price_bp` and `resting_since_ms` rather than a bare `(side, size)` pair (section 16.1, ruling
R126): a model that never sees `L` can compute neither `min(L, bar.open_bp)` nor `no_cross`, and cannot
know that the fee role is `maker`. For a limit fill
`price_source = "limit"`, `base_price_bp = fill_price_bp` and `slippage_bp = 0` (steps 3 and 4 describe
market orders only, and both fields are required in the `filled` event). Size is capped by the same volume
cap **shared with market orders of that bar** (the cap is per bar per market, consumed in the canonical
order of section 3). A zero-volume bar fills no limit order either, with the same `reconstructed`
exemption as step 1. An unfilled remainder rests until `ttl_bars` bars have passed
(`expires_at_ms = placed_at_ms + ttl_bars * interval_ms`) or the market stops being tradable;
`placed_at_ms` is the bar the order was **drained** at, one bar after the bar it was decided at, so
`ttl_bars` counts from the bar the order actually rests.

`abstain` and `target` never leave a resting order; the unfilled remainder of a market order is
reported and dropped.

**Event fills** (amendment C1b, section 17.3, ruling R152) are the fills execution creates without an
agent's order: the two legs of a future's `roll` at the roll record's two prices, and the `forced_flat`
at `last_bar(i)`'s close. They are priced by `pmx.engine.liquidity.event_fill` (never by a
`LiquidityModel`), carry `price_source = "event"`, `slippage_bp = 0`, the taker fee, `origin = "roll"`
or `"forced_flat"` on their `order_placed`, and are the only `order_placed`, `filled` and `fee_charged`
events written in the **settle** phase. A `forced_flat` cover that cash cannot pay goes through
`truncate_for_cash` like any buy and reports the residual (ruling R154); the reopening leg of a `roll` goes
through the same truncation and the short-notional rule of 17.3, and its residual is in the leg's
`unfilled_size` and `unfilled_reason` and in the event's `position_after` (ruling R198). Before pricing any
agent order, `Execution` checks `notional_micro(size_milli, p, tick, point) <= NOTIONAL_CENTS_MAX *
NOTIONAL_DENOMINATOR`, with `p` the limit price of a limit order and `bar.high_bp`, the largest price the
envelope can print (16.1 rule 3), for a market order, and rejects `order_rejected(bad_size)` otherwise
(rulings R147 and R196: this is the one place the cap is checked, and 8.4 lists no `bad_size` for it). On a continuous instrument the cap of step 2, the
slippage of step 4 and the limit rule read `_ticks` where they read `_bp`, `bar.volume_milli` is in
milli-units of the instrument, and a bar with no quote takes the half-spread floor of section 17.4 as its
base (ruling R156).

E2's surface is literal, so E5 can call it blind in the same wave:

```python
class Execution:
    def __init__(self, *, journal: Journal, config: RunConfig,
                 schedules: Mapping[str, FeeSchedule],
                 liquidity: LiquidityModel,                       # section 16.1; keyword-only, required
                 calendars: Mapping[str, SessionCalendar] | None = None,
                 carry_schedules: Mapping[str, CarrySchedule] | None = None) -> None: ...
        # `carry_schedules` (ruling R213): the carry rows by id, CARRY_SCHEDULES of 17.4 by default, which is
        # empty until F2 lands a dataset that declares a rate-differential row. DECLARED, NOT YET IN CODE
        # (rulings R213 and R274): keyword-only t0_ms: int and t1_ms: int, the run's resolved window, which
        # run_backtest computes and passes, so that at the run's last bar execute_bar drains every queued item
        # whose instrument has no later bar as order_rejected(not_tradable) with its decided_at_ms (17.2, 16.2);
        # today such an item is dropped (5 of 1 627 on the demo pack) and
        # tests/test_runner.py::test_every_queued_item_produces_exactly_one_execute_phase_event pins `dropped > 0`.
        # The first engine lot after amendment C1c applies it with R214, R217 and R221 in one commit, reads
        # `dropped == 0` in that test, regenerates the contract fixture and the pinned hashes, and bumps
        # ENGINE_VERSION and CONTRACT_VERSION (13.2).
        # `calendars` is amendment C1b's (ruling R174): the sealed session calendars by id, which the
        # per-instrument queue of 17.2, borrow_fee and carry (one event per session, days since the previous
        # session close) read. None means the synthesised `continuous` calendar for every instrument, which
        # is what a binary run passes; the runner passes {id: dataset.calendar(id)} over the run's kinds.
    def place(self, *, agent_id: str, market: Market, action: MarketAction, item_index: int,
              t_ms: int) -> None: ...
        # Called in the DECIDE phase of bar t_ms. It validates and queues; it emits no event, moves no
        # cent and reserves nothing (amendment C1, section 16.2, ruling R110).
    def pending_market_ids(self, *, t_ms: int) -> tuple[str, ...]: ...
        # The union, in canonical market order, of the markets holding an item place accepted at the
        # instrument's previous bar (t_ms - interval_ms on a `continuous` calendar, ruling R192) and the
        # instruments carrying a resting order of any agent, because a resting order tries against each later
        # bar's range and execute_bar is the only entry point that prices one (rulings R131 and R213).
        # The runner drives execute_bar over exactly this tuple (amendment C1, section 16.2, ruling
        # R131). It is NOT a subset of bar t's tradable set: a market that closed or settled at
        # t - interval_ms is in it and is owed the order_rejected(not_tradable) of step 0, and the
        # runner resolves the Market from the dataset rather than from the bar slice.
    def execute_bar(self, *, t_ms: int, market: Market) -> None: ...
        # Called in the EXECUTE phase of bar t_ms. It drains what place accepted at the instrument's previous
        # bar (t_ms - interval_ms on a `continuous` calendar, ruling R192),
        # in agent_id order then submission order, prices the whole market's batch through one
        # model.quote_bar call, and emits every execute-phase event of section 9.2.
    def settle(self, *, market: Market) -> Mapping[str, int]: ...
        # Pays every position, expires every resting order on the market (reason "settled") and returns
        # {agent_id: cash_delta_cents}. It emits order_expired only: the two scored events of the settle
        # phase (settled, settlement_applied) belong to the runner, which holds the forecast history.
    def mark(self, *, t_ms: int, markets: Sequence[Market],
             agent_ids: Sequence[str] | None = None) -> Mapping[str, PortfolioView]: ...   # None: every registered agent (R213)
    def portfolio(self, agent_id: str) -> PortfolioView: ...
    def position(self, agent_id: str, market_id: str) -> PositionView: ...
    def expire_orders(self, *, t_ms: int, markets: Sequence[Instrument]) -> None: ...
        # The OPEN phase's order_expired (ttl, not_tradable): execution is its one emitter (9.3, ruling R213).
    def register_agent(self, agent_id: str) -> None: ...      # the roster, before any agent's first fill
    def agent_ids(self) -> tuple[str, ...]: ...
    def is_ruined(self, agent_id: str) -> bool: ...
    def ruined_agent_ids(self) -> tuple[str, ...]: ...
    def drain_ruined(self) -> tuple[tuple[str, int, tuple[str, ...]], ...]: ...
        # (agent_id, equity_cents, cancelled_order_ids) of the agents ruined since the previous call: 9.2's
        # agent_ruined needs the cancelled ids and only execution knows them (ruling R213).
    def apply_cash_events(self, *, t_ms: int, market: Instrument) -> None: ...
        # Amendment C1b, section 17.3 (ruling R151). Called in the SETTLE phase for each continuous
        # instrument in canonical order: applies every CashEvent whose application bar (applies_at of 17.3,
        # ruling R175) is t_ms, in (kind order, t_ms, cash_event_id) order (ruling R193), emits
        # cash_event_applied and the event fills of a roll, expires resting orders a split or a roll
        # invalidates. Nothing for an agent whose position is 0 before and after.
    def force_flat(self, *, t_ms: int, market: Instrument) -> None: ...
        # Amendment C1b, section 17.3 (ruling R150). Called in the SETTLE phase at last_bar(i): one event
        # fill per non-flat agent at the bar's close, then cash_event_applied(kind="forced_flat").
```

`Market` in the three signatures above that take one reads `Instrument` (section 17.1): a `Market` is
one, and `settle` is called for binaries only.

### 8.7 Settlement, marking, ruin

- At `settles(m, t)`: every agent with `position != 0` receives `position * 100` cents on YES for a
  positive position, `-position * 100` cents on NO for a negative position, `0` otherwise
  (`settlement_applied.cash_delta_cents`); resting orders on `m` are expired with `reason = "settled"`.
- The two scored fields of the settle phase are computed by the runner through `pmx.scoring`, not by
  execution, which never sees a forecast: `settled.market_brier_tw_micro` and
  `settlement_applied.agent_brier_tw_micro` are section 12.1's time-weighted Brier over the market's
  forecast bars; `settled.n_bars` is the number of the market's bars **inside the run** (the bars where
  `open(m, t)` held between `t0_ms` and `t1_ms`, which is the whole life for a run over the whole dataset)
  and `settlement_applied.n_forecast_bars` the number of `forecast_recorded` events for this
  `(agent, market)`, which equals `n_bars` and is the same for every agent of the roster (section 8.2), so
  the projection rebuilds both from the journal alone;
  `settled.life_mean_price_bp = round_half_up(sum(market_priced.close_bp over those bars), n_bars)`;
  `settlement_applied.realised_pnl_cents = sum(filled.cash_delta_cents) - sum(fee_charged.fee_cents)
  + cash_delta_cents` over this `(agent, market)`.
- Marking (close phase): `mark_price_bp` is **the close of bar `t` itself**, which has elapsed by the time
  the close phase runs, and is deliberately **not** the observation's `last_price_bp` (the close of the
  last *completed* bar at the bar's open, section 5.4). Marking against the previous bar would give a
  different equity, drawdown and ruin series for every agent on every bar, so the two names are distinct
  and only one of them marks. `positions_value_cents = sum over markets of (position * mark_price_bp //
  100)` for YES legs and `(-position * (10_000 - mark_price_bp) // 100)` for NO legs (floor,
  conservative); `equity = cash + positions_value`. `reserved` is inside `cash` (it is cash, earmarked),
  so it is not added again. `peak_equity_cents = max(peak, equity)`;
  `drawdown_bp = bp_ratio(equity - peak, peak)`.
- Ruin: at the close phase, `equity_cents <= ruin_floor_cents` sets `ruined = true`: every resting
  order is expired (`reason = "ruined"`), the agent receives no further observation and no further
  `decide` call, **its forecasts keep being recorded as carried** (section 8.2) so its scored bar set
  matches the market baseline's, and its positions ride to settlement. `agent_ruined` is a selection event
  (section 12.6). Decision D-5 records the non-zero default floor.

**On a continuous instrument** (amendment C1b, section 17.3, rulings R150 and R154) there is no
settlement and nothing to ride to. Marking uses `mark_value_cents(position_milli, close_ticks of bar t,
tick_size_micro, point_value_micro)`, which is `floor` of the notional for a long and `-ceil` for a
short, so `positions_value_cents` is **signed** and `equity = cash + positions_value` may fall below
zero on a short that has run away; ruin is then 8.7's rule unchanged. At `last_bar(i)` every position is
closed by the engine at the bar's close through an event fill (`force_flat`), which pays the taker fee
and is journaled as a fill and never as a mark, and the runner emits `instrument_closed`; a cover that cash
cannot pay is truncated and the residual liability stays in `equity_marked` to the end of the run, marked
at `instrument_closed.last_price_ticks` on every later bar because the instrument has no more bars (ruling
R198). A debit cash event (17.3, ruling R179) lowers cash and equity cent for cent and ruin stays this
rule on equity. A `settled` or `settlement_applied` event is never written for a continuous instrument.

### 8.8 Fee schedules as data (E2, `pmx.engine.fees`)

```python
FEE_MODELS = ("pq_permille", "notional_bp", "per_contract", "zero")     # amendment C1b, section 17.4

@dataclass(frozen=True, slots=True)
class FeeSchedule:
    schedule_id: str
    provider: str
    kind: str = "binary"                # one of INSTRUMENT_KINDS (ruling R155)
    model: str = "pq_permille"          # one of FEE_MODELS; pq_permille is the binary rule below
    taker_permille: int = 0             # pq_permille: multiplier of size * P * (1 - P), in permille of a currency unit
    maker_permille: int = 0
    taker_bp: int = 0; maker_bp: int = 0; sale_bp: int = 0                 # notional_bp (17.4)
    per_contract_cents: int = 0; exchange_cents: int = 0                   # per_contract (17.4)
    min_half_spread_ticks: int = 0      # the floor of the half-spread estimator of 17.4; 0 on every binary schedule
    rounding: str = "ceil"              # every fee rounds up to the next cent
    source_url: str = ""
    as_of_date: str = ""                # ISO date the schedule was read
    note: str = ""

def fee_cents(schedule: FeeSchedule, *, size: int, price_bp: int, role: str,
              side: str = "buy", tick_size_micro: int = BINARY_TICK_SIZE_MICRO,
              point_value_micro: int = BINARY_POINT_VALUE_MICRO) -> int:
    # pq_permille (every binary schedule; size in contracts, price_bp in bp):
    mult = schedule.taker_permille if role == "taker" else schedule.maker_permille
    numerator = mult * size * price_bp * (BP_ONE - price_bp)          # permille * contracts * bp * bp
    return -((-numerator) // 1_000_000_000)                           # ceil(numerator / 1e9) cents
    # notional_bp, per_contract and zero are section 17.4's bodies, reached through the keyword-only
    # defaults above (preamble rule 2, ruling R155); size is then size_milli and price_bp is price_ticks
```

Derivation: Kalshi's published rule is `fee = round_up(0.07 * C * P * (1 - P))` USD with `P` in dollars;
in cents with `P = price_bp / 10_000` and `0.07 = 70 permille` that is `70 * C * p * (10_000 - p) /
10^9` cents, rounded up. Worked: 100 contracts at 5 000 bp cost `175` cents of fee; 10 contracts at 9 000
bp cost `ceil(6.3) = 7` cents.

Shipped schedules (data, not code):

| `schedule_id` | provider | taker | maker | source | as of |
|---|---|---|---|---|---|
| `kalshi-general-2026-09` | kalshi | `70` | `0` | `https://kalshi.com/docs/kalshi-fee-schedule.pdf` | `2026-09-07` (PRD probe); the PDF returned 429 to the contract author on the same day, so D2, the package that may open a socket, re-reads it and updates `as_of_date` and the constants if they moved (ruling R216) |
| `kalshi-reduced-2026-09` | kalshi | `35` | `0` | same PDF; applied to the series listed in `KALSHI_REDUCED_FEE_SERIES` (data in `fees.py`, empty until D2 reads the PDF, ruling R216) | `2026-09-07` |
| `polymarket-zero-2026-09` | polymarket | `0` | `0` | `https://docs.polymarket.com/` (standard markets carry no trading fee) | `2026-09-07` |
| `manifold-zero-2026-09` | manifold | `0` | `0` | `https://manifoldmarkets.notion.site/` (play money, no trading fee) | `2026-09-07` |
| `demo-zero` | demo | `0` | `0` | none | none |

The market's `fee_schedule_id` is set at import; a market order is a taker, a resting limit order that
fills is a maker. Fees are journaled per fill (`fee_charged`) and are the only cash movement that is
neither a fill, a settlement nor a cash event of section 17.3. The five rows above are the `binary`
schedules and are unchanged; the schedules of the other five kinds, and the borrow and carry schedules
(`CarrySchedule`, `CARRY_SCHEDULES`), are section 17.4's table (ruling R155). `FEE_SCHEDULES: Mapping[str,
FeeSchedule]` keyed by `schedule_id` is the declared registry of the rows above (and `BORROW_SCHEDULES`,
`CARRY_SCHEDULES` those of 17.4), from which every caller builds `Execution`'s mapping (ruling R213). The
re-read of the Kalshi PDF this section asks for belongs to D2, the package that may open a socket; until it
runs, the numbers above stand with their `as_of_date` and `KALSHI_REDUCED_FEE_SERIES = ()` (ruling R216).

### 8.9 The accounting invariant

For every agent `a`, at every bar close and at run end, over the journal alone:

```
cash_cents(a)     == bankroll_cents + sum(filled.cash_delta_cents where agent_id == a)
                                    - sum(fee_charged.fee_cents where agent_id == a)
                                    + sum(settlement_applied.cash_delta_cents where agent_id == a)
                                    + sum(cash_event_applied.cash_delta_cents where agent_id == a)     (amendment C1b, 17.3)
cash_cents(a)     >= 0 unless the last event that moved it is a cash_event_applied DEBIT (funding, dividend,
                     borrow_fee or carry with cash_delta_cents < 0): a fill never takes cash below zero, a debit
                     may, and the debit balance is repaid by the next credit (ruling R179)
reserved_cents(a) == sum(order_placed.reserved_cents) - sum(filled.released_cents) - sum(order_expired.released_cents)   (all for a)
reserved_cents(a) <= max(0, cash_cents(a)) at every bar close: the cash event that leaves reserved above
                     max(0, cash) expires every resting order of the agent with reason "debit", which includes
                     every event that takes cash below zero, so reserved == 0 while cash < 0 (rulings R179, R215)
reserved_cents(a) == 0 at run end (every market of the run has settled or been closed)
position(a, i)    == the last position_after written for (a, i) by a filled or a cash_event_applied, where every
                     filled satisfies position_after - position_before == its signed filled size and every
                     cash_event_applied satisfies position_after == position_before for funding, dividend,
                     borrow_fee and carry; == split_position_milli(position_before, numerator, denominator) for
                     split; == the position_after of the last filled named in order_ids for roll and forced_flat,
                     whose position_before is the position before the first event fill (ruling R178)
position(a, i)    == 0 after settlement (binary) and after instrument_closed (continuous), unless the forced flat
                     reports unfilled_reason == "cash", in which case equity_marked carries the liability to the end
positions_value_cents(a) == sum of 8.7's YES and NO values over binaries plus sum of mark_value_cents over
                     continuous positions (signed);  equity_cents(a) == cash_cents(a) + positions_value_cents(a)
```

`filled.cash_delta_cents` already includes the rounding of section 1.2, so the identity is exact. On a
binary the first block is the v2 invariant to the letter (`sum(cash_event_applied)` is empty and the
position line reduces to the signed sum of fills); section 17.3 restates it kind by kind and names the
lines each kind can move. E2's hypothesis tests generate 1 000 fill sequences per kind (random sizes,
sides, prices, quotes, volumes, including zero-volume bars, a funding sign flip, a reverse split on a
short, a roll with a negative gap, a roll with a positive gap on an agent with no free cash, a dividend on
a short, a dividend debit that takes cash below zero, a buy at an ex-date open that receives no dividend, a
buy at a split's effective open that is not multiplied, and a forced flat that cash cannot pay) and
assert every line above; E5 asserts it on the whole demo pack for 50 seeds (AC-3) and E2E-1b on the
mixed fixture (AC-22).

---

## 9. Journal v2

### 9.1 Envelope

Every event is one JSON object per line with these five envelope fields plus its payload:

```
seq: int          1, 2, 3, ... dense, assigned by pmx.journal.Journal and nowhere else
type: str         the event name below
run_id: str       the run this journal belongs to; a foreign run_id is refused
bar_ms: int       the bar the event belongs to; 0 for run_started, sealed_test_opened and every
                  evolution event (evolution_started, generation_started, candidate_scored,
                  generation_closed, evolution_ended); t1_ms for run_ended
phase: str        pre | open | observe | decide | execute | settle | learn | hive | close | generation | post
```

`PHASE_ORDER` (a constant in `pmx.types`, and the order `verify_journal` compares against) is exactly the
list above: `generation` sits between `close` and `post`, because an evolution journal is
`pre` (`evolution_started`), then `generation` (every generation event), then `post`
(`evolution_ended`), all at `bar_ms = 0`. A journal never mixes `generation` with the bar phases: a
backtest journal has no `generation` event and an evolution journal has no bar event.

Ordering guarantees (`verify_journal`): `seq` dense from 1; `bar_ms` never decreases; inside one `bar_ms`
the `phase` never goes backwards in `PHASE_ORDER`; `seq == 1` is `run_started` or `evolution_started`;
`run_ended` (or `evolution_ended`) is the last event; inside a phase the order is the canonical order of
section 3.

`validate_event_dict` dispatches on the event's `type` to the `$defs` entry of `journal.v2.json` the `oneOf`
would have selected and keeps the whole-schema path for an unknown type (ruling R202: the 32-branch `oneOf`
cost 27 ms an event and a 15 000-event journal took seven minutes to validate). `Journal.take_tail() ->
tuple[JournalEvent, ...]` returns the events appended since the previous call and forgets them, so the
runner reads the fills execution just journaled in linear time (ruling R220); `Journal.events` stays the
whole journal.

### 9.2 The backtest catalogue

Every field is typed; `int` fields are integers in the unit their suffix says; `object` fields are
canonical-json-able mappings whose keys are listed.

| Event | Phase | Per | Payload |
|---|---|---|---|
| `run_started` | pre | run | `seed: int`, `engine_version: str`, `contract_version: str`, `rng_algorithm_version: str`, `dataset_name: str`, `dataset_hash: str`, `interval_min: int`, `t0_ms: int`, `t1_ms: int`, `market_ids: list[str]`, `config: object` (`RunConfig.to_dict()`), `config_hash: str`, `folds: object` (`{train_end_ms, validation_end_ms}`), `memory_from_run_id: str|null`, `memory_hash: str|null`, `memory_from_run_t1_ms: int|null`, `contamination_hash: str|null`, `roster: list[object]` each `{agent_id, family, kind: "scripted"|"llm", genome_hash, genome: object, model: str|null, knowledge_cutoff_ms: int|null}`; amendment C1c adds `sensor_catalogue_hash: str` (18.1, ruling R231; declared, optional in the schema until ruling R274's lot) |
| `sealed_test_opened` | pre | claim | `claim_id: str`, `dataset_hash: str`, `genome_hash: str`, `provider: str`, `n_markets: int`, `market_ids: list[str]`; emitted by `open_sealed_test` into the claim's journal, so a read of the sealed fold cannot exist without a record of it (section 12.7) |
| `market_listed` | open | market, once per run, at the first bar where `open(m, t)` holds | `market_id`, `provider: str`, `category: str`, `tags: list[str]`, `event_key: str|null`, `created_at_ms: int`, `close_at_ms: int`, `interval_min: int`, `fee_schedule_id: str`, `hardness_tags: list[str]`, `fold: str`; amendment C1b adds `kind: str`, `vendor: str`, `symbol: str`, `tick_size_micro: int`, `point_value_micro: int`, `session_calendar_id: str`, `borrow_schedule_id: str|null`, `carry_schedule_id: str|null`, required since gate G2 (rulings R164 and R202); on a continuous instrument `close_at_ms` is `delisted_at_ms` or `0` when unset; amendment C1c adds `provider_labels: list[str]`, `subject: list[str]`, `structure: str`, `horizon: str`, `cohort_id: str|null` (7.14, 18.5, rulings R265 and R288; declared, optional in the schema until ruling R274's lot, the projection reading `[]`, `[]`, `""`, `""`, `null` when absent). `cohort_id` is on the wire because the projection rebuilds `results.json` from the journal alone (9.5) and `PerMarket.cohort_id` would otherwise need a second implementation of `pmx.cohorts.list_cohorts`'s keying rule in E5 |
| `market_priced` | open | (bar, open market) | `market_id`, `close_bp: int` (the close of bar `t` itself, the `mark_price_bp` of section 8.7), `last_close_bp: int` (the close of the last completed bar at `t`, else `first_price_bp`: the market's own forecast on this bar), `vwap_bp: int`, `volume_milli: int` |
| `bar_opened` | open | bar | `open_market_ids: list[str]`, `tradable_market_ids: list[str]`, `settling_market_ids: list[str]`, `listed_market_ids: list[str]` (newly listed this bar) |
| `order_expired` | open, settle, close | order | `order_id`, `agent_id`, `market_id`, `remaining_size: int`, `released_cents: int`, `reason: "ttl"|"not_tradable"|"settled"|"ruined"|"corporate_action"|"roll"|"delisted"|"debit"` (the last four are amendment C1b's, section 17.3; `debit` is ruling R179's: a cash-event debit took the agent's cash below zero and every resting order of the agent is expired) |
| `observation_built` | observe | agent | `agent_id`, `n_markets: int`, `n_news: int`, `n_hive: int`, `n_bars_max: int`, `research_remaining: int`, `bytes: int`, `obs_sha256: str`; amendment C1c adds `sensors: list[str]` (the resolved sensor set of `Observation.sensors`, 18.1, ruling R231; declared, optional in the schema until ruling R274's lot) |
| `reply_received` | decide | LLM agent | `agent_id`, `source: "llm"|"fallback"`, `error: str|null` (a `RejectReason`), `schema_valid: bool`, `n_lessons: int` |
| `action_received` | decide | agent | `agent_id`, `source: "scripted"|"llm"|"fallback"`, `intents: list[object]` (validated `MarketAction`s as dicts, sorted by `market_id`), `research: object|null`, `notes: str`, `n_lessons: int`, `n_rejected: int` |
| `action_rejected` | decide | rejected item | `agent_id`, `market_id: str|null`, `scope: "market"|"research"|"notes"|"lessons"|"actions"|"rule"` (`rule` is amendment C1c's, 8.4), `item_index: int`, `reason: str`, `detail: str` |
| `rule_proposed` (declared, R274) | decide | valid `propose_rule` of an agent | `agent_id`, `rule_id: str`, `rule: object` (`Rule.to_dict()`, 18.2), `diet_cost_units: int` (the bar's diet cost including the proposal's unit); amendment C1c, ruling R237: declared under `$defs` of `journal.v2.json` and admitted to `oneOf` by ruling R274's lot with its `pmx.journal` dataclass (the discipline of R164) |
| `workflow_step_executed` (declared, R274) | decide | (agent with `Genome.workflow` not `None`, step) | `agent_id`, `step_index: int`, `kind: str` (one of `STEP_KINDS`), `ref: str|null`, `n_inputs: int`, `n_out: int`, `output_sha256: str` (18.4, ruling R243; digest only, so the payload is bounded by construction; never emitted for a linear genome). Declared and admitted as the row above |
| `forecast_recorded` | decide | (agent, open market) | `agent_id`, `market_id`, `prob_ppm: int`, `carried: bool`; on a continuous instrument also `price_ref_ticks: int` and `horizons: list[object]` each `{horizon_bars, up_probability_ppm, quantiles_ticks: list[int]|null}` (amendment C1b, section 17.5, ruling R157; absent on a binary) |
| `research_spent` | decide | request | `agent_id`, `kind: str`, `market_id: str|null`, `units: int`, `remaining: int`, `granted: bool` |
| `memory_written` | decide (LLM lessons), learn | write | `agent_id`, `kind: "calibration"|"prior"|"feature"|"lesson"|"note"`, `key: str`, `payload: object`, `bytes_after: int` |
| `order_placed` | execute | order | `order_id`, `agent_id`, `market_id`, `kind: "market"|"limit"`, `side: "buy"|"sell"`, `price_bp: int|null`, `size: int`, `ttl_bars: int|null`, `expires_at_ms: int|null`, `reserved_cents: int`, `origin: "target"|"limit"|"abstain"|"roll"|"forced_flat"`, `decided_at_ms: int` (the bar the intent was decided at: the instrument's previous bar, which is `bar_ms - interval_ms` on a `continuous` calendar and Friday's last bar for a Monday fill on a session calendar, section 16.2 and ruling R192; the bar itself for an event fill, whose phase is `settle`, section 17.3) |
| `order_rejected` | execute | intent | `agent_id`, `market_id`, `item_index: int`, `reason: str` (`not_tradable`, `ruined`, `no_liquidity` and the validation reasons; a free string, not an enum), `detail: str`, `decided_at_ms: int` |
| `filled` | execute | fill | `order_id`, `agent_id`, `market_id`, `side`, `kind`, `requested_size: int`, `filled_size: int`, `unfilled_size: int`, `unfilled_reason: "none"|"volume_cap"|"cash"|"zero_volume"|"no_cross"|"no_liquidity"`, `base_price_bp: int`, `slippage_bp: int`, `fill_price_bp: int`, `price_source: "open"|"quote"|"limit"|"impact"|"mm"` (plus `"event"` for an event fill of section 17.3, ruling R152, the one case whose phase is `settle`), `close_size: int`, `open_size: int`, `cash_delta_cents: int`, `released_cents: int`, `position_before: int`, `position_after: int`, `avg_cost_bp_after: int` |
| `fee_charged` | execute | fill | `order_id`, `agent_id`, `market_id`, `fee_cents: int`, `schedule_id: str`, `role: "taker"|"maker"` |
| `settled` | settle | market | `market_id`, `outcome: int`, `payout_bp: int`, `resolved_at_ms: int`, `n_bars: int`, `market_brier_tw_micro: int`, `life_mean_price_bp: int` (section 8.7 defines the last two) |
| `settlement_applied` | settle | (agent, market) with a position or a forecast | `agent_id`, `market_id`, `position: int`, `cash_delta_cents: int`, `cash_after_cents: int`, `realised_pnl_cents: int` (fills + settlement - fees on this market), `agent_brier_tw_micro: int`, `n_forecast_bars: int` |
| `hive_written` | hive | entry | `entry_id`, `kind: "forecast"|"resolution"|"lesson"|"reputation"|"insight"` (`insight` is amendment C1c's, 18.2, ruling R239: written by the optimizer at generation close and by L1 daily into the hive snapshot, never by an agent), `author_id: str` (`"engine"` for resolution and reputation; the rule's author for an insight), `market_id: str|null`, `visible_from_ms: int`, `payload: object` |
| `equity_marked` | close | agent | `agent_id`, `cash_cents` (signed since ruling R179: a debit cash event may leave a debit balance), `reserved_cents`, `positions_value_cents` (signed since amendment C1b: a short on a continuous instrument is a liability, ruling R154), `equity_cents` (signed, rulings R154 and R180), `fees_paid_cents`, `peak_equity_cents`, `drawdown_bp` (`<= 0`, below `-10_000` when equity is negative, ruling R180), `n_open_positions: int`, `n_open_orders: int` |
| `agent_ruined` | close | ruined agent | `agent_id`, `equity_cents: int` (signed, ruling R180), `cancelled_order_ids: list[str]` |
| `bar_closed` | close | bar | `n_events: int` (events of this bar including itself) |
| `cash_event_applied` | settle | (agent, continuous instrument, cash event) with a non-zero position before or after | `agent_id`, `market_id`, `cash_event_id: str`, `kind: "funding"|"dividend"|"split"|"roll"|"borrow_fee"|"carry"|"forced_flat"`, `origin: "data"|"engine"`, `position_before: int`, `position_after: int` (for `roll` and `forced_flat` the position before the first and after the last event fill named in `order_ids`, ruling R178), `avg_cost_ticks_before: int`, `avg_cost_ticks_after: int`, `cash_delta_cents: int` (`0` for `split`, `roll` and `forced_flat`, whose money moves in their `filled` and `fee_charged`; signed for the other four and may take cash below zero, ruling R179), `order_ids: list[str]`, `detail: object` (amendment C1b, section 17.3) |
| `instrument_closed` | settle | continuous instrument, once, at `last_bar(i)` | `market_id`, `kind: str`, `reason: "window_end"|"delisted"`, `last_price_ticks: int`, `n_bars: int`, `n_forecasts_unresolved: int` (section 17.3) |
| `forecast_resolved` | settle | (agent, continuous instrument, forecast bar, horizon) at the bar the realisation became public | `agent_id`, `market_id`, `forecast_bar_ms: int`, `horizon_bars: int`, `up_probability_ppm: int`, `quantiles_ticks: list[int]|null`, `price_ref_ticks: int`, `price_realised_ticks: int`, `realised_sign: int` (`-1`, `0`, `1`), `directional_brier_micro: int`, `pinball_micro: int|null`, `baseline_pinball_micro: int`, `carried: bool` (section 17.5, ruling R160) |
| `run_ended` | post | run | `reason: "completed"|"aborted"`, `final_bar_ms: int`, `n_bars: int`, `event_count: int`, `ruined_agent_ids: list[str]` |

`decided_at_ms`, the two widened enums and `no_liquidity` are amendment C1's edits to this catalogue, and
they are applied **here**, in the document C1 owns, rather than deferred to the gate (ruling R129).
`price_source` no longer lists `vwap`: the fallback base moved to the execution bar's open (ruling R113)
and no `LiquidityModel` may return the old spelling (ruling R138). `src/pmx/schemas/journal.v2.json` is
widened in the same pass and keeps `vwap` in its enum so a journal written before the amendment still
validates; `decided_at_ms` is `required` there since gate G2 (rulings R129 and R202), when `pmx.journal` (D7) gained
it; the shipped `tests/fixtures/contract/journal.backtest.jsonl` is a pre-latency journal the gate
**completed** (`decided_at_ms = bar_ms`, R164's eight `market_listed` fields, the two `forecast_recorded`
nulls) and never regenerates, because its documented differences from a latency-correct run are what E5's
reproduction tests measure.

Amendment C1b's three rows above **are** in `journal.v2.json`'s `oneOf` since gate G2 (rulings R164 and
R202), which gave `pmx.journal` (D7) their dataclasses, and the `settle` phase of the three execute-phase
events of an event fill is in the schema's phase enum and the classes' `PHASES` since the same commit (the
discipline of R129: D7's tests pin the schema's `oneOf` and phase
enums to its classes, so a schema ahead of the classes would refuse the journals the engine wave must
write). Every other widening is applied now: the enums of `order_expired.reason`, `order_placed.origin`
and `filled.price_source`, the signed `equity_marked.positions_value_cents`, the `market_listed`
and `forecast_recorded` fields (`required` since gate G2, ruling R202), the id patterns and the tick and milli bounds (rulings R148, R152, R160,
R165). On a continuous instrument `market_priced` carries ticks in its three price fields and
`close_at_ms` of `market_listed` reads `delisted_at_ms`.

`market_listed` and `market_priced` are **observed inputs**, not derived numbers, which is why adding
them does not breach section 9.5's rule against widening a journal with a projection's output. They are
there because `pmx replay` must rebuild `results.json` from `journal.jsonl` alone, and without them it
cannot: the horizon buckets and the per-bucket market Brier of section 12.1 need `close_at_ms` and the
per-bar market price, `pmv_bp` needs `price_{t + h}`, `contrarian_bp` needs the price on every forecast
bar, `block_key` and therefore every `Interval` need `event_key`, and section 12.10's per-category,
per-hardness-tag and per-fold rows need `category`, `hardness_tags` and `fold`. A projection that reads
the dataset instead would break the replay guarantee of section 6.4 and AC-3.

The `forecast` hive entry written at `decide` for `(agent, market, bar)` carries
`visible_from_ms = bar_of(resolved_at_ms) + interval_ms` of the market (known to the engine, never to
agents), so the as-of filter releases it at the **first bar strictly after** the settling bar. Neither
`resolved_at_ms` itself nor the settling bar's own open would do: the observe phase runs before the settle
phase, so `visible_from_ms == resolved_at_ms` on a venue that settles on the bar grid (routine for Kalshi
and for every 00:00Z settlement) would show every agent every other agent's forecast on a market that is
still open and that they are about to forecast in the same bar, which section 7.9 forbids; and an
off-grid `resolved_at_ms` would make the entries visible only after the run ended, so the calibrator's
pooling and the resolution history would silently see nothing. `hive_written(kind="forecast")` is emitted
in the `hive` phase of the bar of the forecast, one per `forecast_recorded`, and is the reason
`hive_written` volume is the largest in the journal.

`--no-hive` keeps the writes and empties the reads; `--amnesic` starts from an empty memory. Both change
`run_started.config` and therefore the journal hash, and **that alone is not evidence of anything**: the
bytes differ because the config bytes differ, so a test that only compares hashes would pass even if
neither switch changed a single decision. **AC-5 is therefore behavioural**, and E5's test states it that
way: with the `run_started` event excluded from both journals, at least one `forecast_recorded.prob_ppm`
differs for a hive-reading agent (`stacker`, `calibrator`) and at least one differs for a memory-reading
agent, and the reported skill delta is computed from the two `results.json` files, never from the two
hashes. A pair of runs whose non-`run_started` events are identical **fails** that test.

### 9.3 One emitter per event

| Event | The one module that emits it |
|---|---|
| `run_started`, `bar_opened`, `market_listed`, `market_priced`, `observation_built`, `reply_received`, `action_received`, `action_rejected`, `forecast_recorded`, `research_spent`, `settled`, `settlement_applied`, `bar_closed`, `run_ended`, `agent_ruined`, `equity_marked`, and amendment C1c's `rule_proposed` and `workflow_step_executed` (section 18) | `engine/runner.py` (E5) |
| `family_registered`, `rule_tested`, `rule_promoted`, `rule_demoted` (amendment C1c, 9.4) | `rules/tester.py` (S2), into the evolution journal `optimizer/evolution.py` hands it, or into the standalone ledger of 18.2 |
| `order_placed`, `order_rejected`, `filled`, `fee_charged`, `order_expired` | `engine/execution.py` (E2), through the `Journal` the runner hands it |
| `cash_event_applied` | `engine/execution.py` (E2), inside `apply_cash_events` and `force_flat` (section 17.3) |
| `forecast_resolved` | `engine/runner.py` (E5), which holds the forecast history and the price lookups of section 17.5 |
| `instrument_closed` | `engine/runner.py` (E5), after `Execution.force_flat` returns |
| `sealed_test_opened` | `optimizer/folds.py` (O1), inside `open_sealed_test`, into the journal its one caller hands it |
| `memory_written` | `agents/memory.py` (A2) |
| `hive_written` | `agents/hive.py` (A3) |
| `evolution_started`, `generation_started`, `candidate_scored`, `generation_closed`, `evolution_ended` | `optimizer/evolution.py` (O2) |

`settled` and `settlement_applied` moved from E2 to E5 in wave 0: their payloads carry
`market_brier_tw_micro`, `agent_brier_tw_micro`, `n_forecast_bars` and `life_mean_price_bp`, none of which
`Execution` can compute (it never sees a forecast) and none of which is in its scope. `Execution.settle`
returns the per-agent cash deltas and emits `order_expired(reason="settled")` only (section 8.6).

One event per money movement: a cent moves in exactly one of `filled.cash_delta_cents`,
`fee_charged.fee_cents`, `settlement_applied.cash_delta_cents`, `cash_event_applied.cash_delta_cents`
(amendment C1b: a `roll` and a `forced_flat` move their money through their event fills and carry `0`
there, ruling R151). Reservations move in exactly one of
`order_placed.reserved_cents`, `filled.released_cents`, `order_expired.released_cents`.

### 9.4 The evolution catalogue

An evolution run has its own journal in `runs/<evo_run_id>/journal.jsonl`, with `bar_ms = 0`
throughout, `phase = "pre"` for `evolution_started`, `phase = "generation"` for `generation_started`,
`candidate_scored` and `generation_closed`, and `phase = "post"` for `evolution_ended` (which is what
`journal.v2.json` pins and what `PHASE_ORDER` of section 9.1 accepts). It references the backtest
run ids it produced, which differ between the training and the validation fold because `fold` and
`market_ids_hash` are in the config (section 8.1).

| Event | Payload |
|---|---|
| `evolution_started` | `seed`, `engine_version`, `contract_version`, `dataset_hash`, `config: object` (`EvolutionConfig.to_dict()`), `config_hash`, `population_size: int`, `max_generations: int`, `folds: object` (`{train_end_ms, validation_end_ms, n_train, n_validation, n_sealed}`), `initial_population: list[object]` (`{agent_id, family, genome_hash, genome}`) |
| `generation_started` | `generation: int`, `run_seed: int`, `train_run_id: str`, `validation_run_id: str`, `population: list[str]` (agent ids) |
| `candidate_scored` | `generation`, `agent_id`, `genome_hash`, `fold: "train"|"validation"`, `n_markets: int`, `skill_point_micro`, `skill_lb_micro`, `pnl_point_cents`, `pnl_lb_cents`, `brier_tw_micro`, `ruined: bool`, `research_units_spent: int`, `descriptors: object` (section 12.5, `diet_class` included); amendment C1c adds `tier: "proxy"|"engine"`, `matrix_hash: str|null` and `features_hash: str|null` (the proxy tier's inputs, 12.6, ruling R254; `null` on the engine tier), `diet_cost_units: int`, `sensors: list[str]`, `n_rules_proposed: int` (18.1, ruling R235); the six are declared, optional in the schema until gate G4 lands O2's dataclasses |
| `family_registered` (declared, gate G4) | `generation`, `family_id: str`, `template: object` (`FamilyTemplate.to_dict()`, 18.2), `n_candidates: int`, `n_screened: int`, `fit_t1_ms: int`, `registered_at_ms: int`; written **before** any `rule_tested(stage="replicate")` of the family (ruling R238) |
| `rule_tested` (declared, gate G4) | `generation`, `rule_id`, `family_id`, `stage: "fit"|"replicate"|"live"|"transfer"`, `fold: str` (the fold or fold pair read), `target: str|null` (a provider, category or kind on `transfer`), `support: int`, `n_markets: int`, `effect: object` (`Interval.to_dict()`, in bp), `usual_bp: int|null` (volatility claims), `p_value_ppm: int|null`, `fdr_m: int|null`, `fdr_k: int|null`, `fdr_passed: bool|null` (replicate stage only), `passed: bool` |
| `rule_promoted` (declared, gate G4) | `generation`, `rule_id`, `family_id`, `author_kind`, `author_id`, `fit_t1_ms: int`, `visible_from_ms: int` (`fit_t1_ms + interval_ms`), `entry_id: str` (the hive `insight` entry) |
| `rule_demoted` (declared, gate G4) | `generation`, `rule_id`, `reason: "live_negative"|"author_reputation"`, `live_support: int`, `live_effect: object`, `demoted_at_ms: int` |
| `generation_closed` | `generation`, `ranked: list[object]` (`{agent_id, genome_hash, skill_lb_micro, pnl_lb_cents, rank}`), `culled: list[str]`, `elites: list[str]`, `children: list[object]` (`{agent_id, genome_hash, genome, op: "mutation"|"crossover"|"structural"|"immigrant"|"prompt_mutation"|"sensor_drop", parents: list[str]}`; `sensor_drop` is amendment C1c's, 18.1), `archive: list[object]` (`{cell_key, agent_id, genome_hash, skill_lb_micro}`), `archive_filled: int`, `archive_cells: int`, `hall_of_fame: list[object]` (`{family, genome_hash, genome, skill_lb_micro, run_id}`), `candidates_evaluated_cum: int`, `best_validation_lb_micro: int`, `patience_left: int`, `research_budget_next: object` (`{agent_id: units}`); amendment C1c adds `sensor_budget_next: object` (`{agent_id: units}`), `culled_by_budget: list[str]`, `rule_rewards: list[object]` (`{agent_id, rule_id, kind: "promoted"|"rejected"|"demoted", skill_bonus_micro, sensor_units}`), `n_engine_tier: int` and `n_proxy_tier: int` (12.6, rulings R235, R239, R254; declared, optional until gate G4) |
| `evolution_ended` | `reason: "max_generations"|"patience"|"aborted"`, `generations_run: int`, `candidates_evaluated_cum: int`, `champion: object` (`{agent_id, genome_hash, genome, validation_skill_lb_micro}`) |

A row whose name carries **`(declared, <applier>)`**, here and in 9.2, is declared and not yet in the
catalogue: its definition is under `$defs` of `journal.v2.json` (applied by this amendment) and outside
`oneOf`, and the named applier admits it to `oneOf`, to `EVENT_TYPES` and to the catalogue proper in one
commit with its `pmx.journal` dataclass (the discipline of rulings R129 and R164: D7's tests pin `oneOf` to
the classes, and `tests/test_contract_schemas.py` pins the catalogue rows to `oneOf`, so the three move
together or not at all). The four rule events above are gate G4's, with O2's evolution journal; the
widenings of `candidate_scored` and `generation_closed` are optional in the schema until the same commit.

`hall_of_fame`, `archive` and `champion` only ever name a
genome scored at the **engine** tier (12.6, ruling R254): a proxy score selects who gets a full replay and
nothing more.

`candidates_evaluated_cum` counts **distinct genome hashes ever scored on the validation fold** in this
evolution run, **at either tier** (a proxy score is a look at the validation fold and deflation counts
looks, ruling R254); it is one of the three inputs to the `K` of the deflation in section 12.4 and is copied
into the claim. It is `0` for a generation that scored no candidate on the validation fold (validation
runs every `k` generations), so both the `generation_closed` and the `evolution_ended` field are
non-negative, never strictly positive.

`generation_closed.research_budget_next` is applied by giving the next generation's backtest a
`RunConfig.research_budget_by_agent` (section 8.1) built from it; the adjustment rule is in section 12.6.

### 9.5 Artefacts on disk

```
runs/<run_id>/
  manifest.json      run_id, kind, seed, dataset_name, dataset_hash, market_ids_hash, fold, config,
                     config_hash, roster (with genomes), journal_hash, engine_version, contract_version,
                     rng_algorithm_version, memory_snapshots {agent_id: object}, agent_snapshots
                     {agent_id: object}, hive_snapshot: object|null, memory_hash: str|null           (E5)
  journal.jsonl      the journal; hashed; replays the run                          (D7's Journal, driven by E5)
  journal.sha256     "<hex>  journal.jsonl\n"                                       (E5)
  results.json       the projection (section 12); rebuilt by pmx replay and compared (E5)
  llm_trace.jsonl    cost, latency, tokens, attempts, raw text, rationale; not hashed (A5)
  observations/      optional, --dump-observations: <bar_ms>-<agent_id>.json for the leak audit (E1's renderer, E5 writes)
claims/<claim_id>.json, claims/access.jsonl                                          (O4)
live/forecasts.jsonl, live/resolutions.jsonl                                         (L1)
rules/<dataset_hash[:8]>/families.jsonl, rules/<dataset_hash[:8]>/rules.jsonl        (S2; TRACKED like claims/,
                     the rule ledger of 18.2: one canonical line per family_registered, rule_tested,
                     rule_promoted and rule_demoted, chained by prev_sha256; the rule_proposed rows
                     `pmx rules ledger` renders are copied from the run journals, ruling R294)
audits/<dataset_hash[:16]>/linker.json, audits/<dataset_hash[:16]>/taxonomy.json    (gate G3 fills the verdicts;
                     DS1 and DS2 write the files; TRACKED, outside the dataset hash, rulings R250, R268, R296)
```

`memory_snapshots` is `Memory.snapshot()` per agent, `agent_snapshots` is `Agent.snapshot()` per agent
(section 10.2) and `hive_snapshot` is the hive's serialised entry log; the next run loads them by naming
this run in `config.memory_from_run_id` and `config.hive_from_run_id` (section 8.1), which is the whole
mechanism behind "memory persists across runs", the fold carry-forward of section 12.7 and the claim
freeze of section 12.8. Nothing else carries state between runs.

The two live files are one canonical JSON object per line (section 4.2):

```
live/forecasts.jsonl    {"forecast_id": "lf-<yyyymmdd>-<agent_id>-<market_id>", "agent_id", "market_id",
                         "provider", "prob_ppm", "forecast_at_ms", "genome_hash", "run_id", "dataset_hash",
                         "model": str|null, "forecast_hash",         forecast_hash per section 4.3
                         "kind", "bar_ms", "price_ref_ticks", "horizons"}   the forecast.v1.json core (ruling R195)
live/resolutions.jsonl  {"market_id", "provider", "outcome", "resolved_at_ms", "life_mean_price_bp",
                         "observed_at_ms", "source_url"}
```

`pmx replay <run_id>` reads `journal.jsonl`, verifies `journal.sha256`, rebuilds `results.json` through
`pmx.metrics.projection` alone (no dataset, no agents, no gateway) and asserts byte equality with the
stored file. A `results.json` that cannot be rebuilt from the journal is a bug in the projection, never a
reason to widen the journal with a derived number.

---

## 10. Agents: protocols and families

### 10.1 `Genome` (`pmx.agents.protocol`, serialised by `pmx.agents.registry`)

```python
@dataclass(frozen=True, slots=True)
class GeneSpec:
    name: str; lo: int; hi: int; step: int; default: int      # inclusive range; step is the mutation sigma

@dataclass(frozen=True, slots=True)
class Genome:
    family: str
    genes: tuple[tuple[str, int], ...]     # sorted by name; every value inside its GeneSpec range
    inner: "Genome | None"                 # composition: this family wraps inner (depth <= COMPOSITION_DEPTH_MAX = 3)
    members: tuple["Genome", ...]          # ensembles only (stacker); () for every other family
    prompt: "PromptGenome | None"          # LLM agents only (section 11.4)
    card: "ModelCard | None" = None        # torch_policy only (amendment C1, 16.5, ruling R119); always rendered, null otherwise
    sensors: tuple[str, ...] = SENSOR_NAMES   # amendment C1c, 18.1, ruling R230: the sensor gene, sorted, unique,
                                           # always containing "tape"; the explicit full tuple for the v1 archetypes
    workflow: "Workflow | None" = None     # amendment C1c, 18.4, ruling R243: None is the linear composition above
    def to_dict(self) -> dict[str, object]: ...
        # {"family", "genes": {name: value}, "inner": ..., "members": [...], "prompt": ..., "card": ...,
        #  "sensors": [...], "workflow": ...}: every key always present, so genome_hash is defined once and for all
    @property
    def genome_hash(self) -> str: ...                  # sha256(canonical_json(self.to_dict()))
```

`card`, `sensors` and `workflow` are the three components amendments C1 and C1c added; A1 ships all three
in lot 6, when no genome hash exists yet and the addition is free (the argument of ruling R119); the
genomes of `tests/fixtures/contract/journal.evolution.jsonl` are completed with the three keys at their
defaults by gate G4, the way gate G2 completed the backtest fixture (ruling R202), and `journal.v2.json`'s
`genome` definition accepts them as optional until then. A genome that omits `tape`, names a sensor outside
`SENSOR_NAMES`, or lacks a sensor its family, `inner` or a `member` requires (`FamilySpec.required_sensors`
below) is refused by `genome_from_dict` and by `make_agent` with `InvalidConfigError` (18.1).

`members` exists because the `stacker` of section 10.5 weights "the members it is composed with" and a
single `inner` cannot represent them: without it the family has no member set, its weighted mean divides
by zero on every market it has not yet seen resolved, and A4's done-when ("the stacker's weight on the
known-good member converges") is not reachable. It is `()` for every other family, it is always present in
`to_dict()` (so `genome_hash` is defined once and for all), and it counts toward the depth cap.

Gene values are integers; mutation adds `round_half_up(step * z)` with `z ~ normal(0, 1)` from
`evolution.mutation`, clamps to `[lo, hi]`, and with probability `config.reset_permille / 1000` (an
`EvolutionConfig` field, section 12.11) draws uniformly in the range instead. Crossover is uniform per
gene between two genomes of the same family (and recurses into `inner`, and pairwise into `members`, when
both have them). Structural mutation swaps `family` for another of the same role (belief, overlay), or
wraps the genome in an overlay, within the depth cap; on a genome with an explicit `workflow` it adds,
removes or rewires a step within 18.4's bounds and returns the parent unchanged when the result breaches
one (ruling R243). Sensor mutation adds or removes one sensor of the catalogue with probability
`sensor_mutation_permille` (never `tape`, never a required one); sensor crossover is uniform per sensor
name; the **sensor drop** of 18.1 is the optimizer's deterministic narrowing of a child that exceeds its
allowance (`op = "sensor_drop"`). Every operation is a pure function of `(genome(s), rng, config)`.

The registry is data, so O2 can drive it blind (A1 owns all of it):

```python
@dataclass(frozen=True, slots=True)
class FamilySpec:
    family: str                                  # section 2's family regex
    role: str                                    # "belief" | "overlay" | "ensemble"
    genes: tuple[GeneSpec, ...]                  # sorted by name
    evolvable: bool                              # False for `legacy`: never a mutation or crossover target
    make: Callable[[str, Genome], Agent]         # (agent_id, genome) -> a live agent
    required_sensors: frozenset[str] = frozenset()   # amendment C1c, 18.1: the sensors the family's rule reads;
                                                 # no operator produces, and no constructor accepts, a genome whose
                                                 # sensors omit one of its family's, its inner's or a member's

FAMILIES: Mapping[str, FamilySpec]               # keys sorted, section 10.5's table exactly
DEFAULT_ROSTER: tuple[tuple[str, Genome], ...]   # (agent_id, genome), the eight v1 names of section 10.5

def make_agent(agent_id: str, genome: Genome) -> Agent: ...
def genome_from_dict(payload: Mapping[str, object]) -> Genome: ...      # raises SchemaError on a bad shape
def mutate(genome: Genome, *, rng: random.Random, config: EvolutionConfig) -> Genome: ...
def crossover(a: Genome, b: Genome, *, rng: random.Random) -> Genome: ...
def structural_mutate(genome: Genome, *, rng: random.Random, config: EvolutionConfig) -> Genome: ...
def random_genome(*, rng: random.Random, config: EvolutionConfig) -> Genome: ...        # immigrants
```

A member the engine only reads (`family`, `agent_id`, `genome`, `needs_gateway`, `kind`, `model`,
`knowledge_cutoff_ms`) is declared **read-only** in any structural protocol that stands in for these types
(ruling R205): `Genome` is `frozen=True`, and a protocol that declared a mutable attribute would be satisfied
by no frozen dataclass at all.

### 10.2 `Agent`

```python
class Agent(Protocol):
    # The seven attributes below are read by the engine and never written: a structural stand-in for this
    # protocol declares them read-only (ruling R205).
    agent_id: str
    family: str
    genome: Genome
    needs_gateway: bool                    # True for LLM agents; the runner routes them through the gateway
    kind: str                              # "scripted" | "llm"; journaled in run_started.roster
    model: str | None                      # the model id for an LLM agent, None for a scripted one
    knowledge_cutoff_ms: int | None        # the model's declared cutoff, None for a scripted one

    def reset(self, *, rng: random.Random, memory: Memory, config: RunConfig) -> None: ...
        """Called once per run after run_started, in agent_id order. rng is the agent's own substream."""
    def observe(self, obs: Observation) -> None: ...
    def receive(self, reply: AgentReply) -> None: ...
        """LLM agents only: the gateway's reply for the bar observed last. Scripted agents raise.
        AgentReply is declared in pmx.types (section 11.1), not in pmx.gateway, so that this protocol and
        the runner's signature can be annotated without breaking rule 1 of the architecture test."""
    def decide(self) -> Actions: ...
        """Pure given (genome, memory, last observation, rng) for scripted agents; for LLM agents a
        pure function of the received reply (validated payload or fallback)."""
    def learn(self, event: ResolutionEvent) -> None: ...
        """Called in the learn phase for every settled market the agent forecast or held. May write memory."""
    def snapshot(self) -> dict[str, object]: ...
        """Internal state beyond memory, canonical-json-able; journaled by the runner at run end in manifest.json."""
    def restore(self, state: Mapping[str, object]) -> None: ...
    def explain(self) -> Explanation: ...
        """(agent_id, bar_ms, features: tuple[(name, value_int)], text: str) for the UI; never journaled."""

@dataclass(frozen=True, slots=True)
class ResolutionEvent:
    market_id: str; category: str; tags: tuple[str, ...]; provider: str
    outcome: int; resolved_at_ms: int; close_at_ms: int; created_at_ms: int
    cohort_id: str | None = None                  # amendment C1c, 18.5: the market's cohort, None when it has none
    forecasts: tuple[tuple[int, int], ...]        # (bar_ms, prob_ppm) the agent stated, oldest first
    market_prices: tuple[tuple[int, int], ...]    # (bar_ms, close_bp) on the same bars
    realised_pnl_cents: int; fees_cents: int
    agent_brier_tw_micro: int; market_brier_tw_micro: int
```

`kind`, `model` and `knowledge_cutoff_ms` are attributes of the protocol because `run_started.roster`
journals them per agent and the runner has no other path to a model id: `ModelSpec` and `LlmSeatConfig`
live in A5 and are handed to the gateway, not to the runner. A scripted agent reports
`("scripted", None, None)`.

The default `learn` of a scripted family updates the calibration ledger and the category priors through
`Memory`; `follower` with the baseline genome writes nothing (so the market-follower identity holds with or
without memory).

### 10.3 `Memory` (`pmx.agents.memory`, A2)

```python
MEMORY_MAX_BYTES = 262_144           # canonical JSON of the whole memory
LESSONS_MAX = 50
NOTES_MAX = 200
CALIBRATION_BINS = 10                # ppm deciles: bin = min(9, prob_ppm // 100_000)
HORIZON_BUCKETS = ("30d", "7d", "2d", "0d")   # days to close_at: >= 30 -> 30d; [7, 30) -> 7d; [2, 7) -> 2d; < 2 -> 0d
RE_HORIZON_BUCKET = re.compile(r"^(30d|7d|2d|0d|h[0-9]{1,5})$")   # a bucket string: the four above or h<bars>
# HORIZON_BUCKETS stays these four (ruling R188): horizons are per-run config and this is a module constant,
# so a continuous bucket is validated by RE_HORIZON_BUCKET and never looked up in the tuple.
# Amendment C1b (17.5, ruling R161): a continuous ledger is keyed (kind, f"h{horizon_bars}", bin) through the
# same CalibrationBin, with `category = kind` and a horizon string "h<n>" per declared horizon; n_yes is
# kept as n_yes_x2 (an up adds 2, a flat realisation adds 1) so a tie is half a yes and nothing is dropped;
# CalibrationBinView.to_dict() renders n_yes_x2 always (ruling R217).
# The last bucket is `< 2`, not `[0, 2)`: section 5.3 keeps a market open between close_at_ms and
# resolved_at_ms, where days_to_close is negative, and `0d` absorbs those settlement-lag bars.

class Memory(Protocol):
    agent_id: str
    frozen: bool
    def record_outcome(self, event: ResolutionEvent, *, written_at_ms: int) -> None: ...   # ledger + priors
    def calibration(self, *, category: str | None, horizon: str | None,
                    cohort_id: str | None = None) -> tuple[CalibrationBin, ...]: ...
        # amendment C1c (18.5, ruling R266): the ledger is keyed (cohort_id or category, horizon_bucket, bin), so
        # a bin is per cohort when the market has one and per category otherwise; ResolutionEvent carries cohort_id
        # (10.2) and record_outcome increments both the cohort's bin and the category's, which is what lets
        # `calibrator` read the cohort first and fall back to the category below min_n
    def prior(self, *, category: str | None, tag: str | None) -> tuple[int, int]: ...   # (n, n_yes)
    def feature_stat(self, family: str, key: str) -> FeatureStat: ...      # (n, sum_milli, sum_sq_milli)
    def add_feature(self, family: str, key: str, value_milli: int, *, written_at_ms: int) -> None: ...
    def add_lesson(self, text: str, market_ids: tuple[str, ...], *, written_at_ms: int) -> None: ...
    def add_note(self, text: str, market_id: str | None, *, written_at_ms: int) -> None: ...
    def view(self, *, now_ms: int) -> MemoryView: ...      # filtered to records with written_at_ms <= now_ms
    def snapshot(self) -> dict[str, object]: ...
    def restore(self, state: Mapping[str, object]) -> None: ...
    def freeze(self) -> None: ...        # every later write raises FrozenMemoryError
    def size_bytes(self) -> int: ...
```

**Every record carries `written_at_ms`**, including a calibration bin and a prior (`last_written_at_ms`
on the bin, and the bin's counts are only ever incremented, never rewritten), and `view(now_ms=...)`
filters to `written_at_ms <= now_ms`. Memory was otherwise the one channel into an observation with no
as-of filter at all, and section 7.9's poisoned-future test now injects a memory record stamped after
`now_ms` alongside the future bar, the future news item and the future hive entry.

Every write emits exactly one `memory_written` through the `Journal` the memory was constructed with, and
is refused with `MemoryFullError` when `size_bytes()` would exceed `MEMORY_MAX_BYTES` (lessons and notes
evict oldest-first before refusing; ledgers never evict). The constructor is literal, because A2 lands in
wave 3 while E5 must construct one in wave 2:

```python
class AgentMemory(Memory):                       # pmx.agents.memory
    def __init__(self, *, agent_id: str, journal: Journal, config: RunConfig,
                 snapshot: Mapping[str, object] | None = None) -> None: ...
```

Memory persists across runs of the same `agent_id` through
`runs/<run_id>/manifest.json.memory_snapshots` (section 9.5) and is loaded by the next run from
`config.memory_from_run_id` (section 8.1), which is in `config_hash` and is journaled with its hash and
the source run's `t1_ms` in `run_started`; the runner raises `LeakError` when that `t1_ms > t0_ms`.
`--amnesic` starts from an empty memory and stores nothing. A claim run (section 12.8) loads the memory
snapshot of the run that ended at `validation_end_ms` and calls `freeze()` before the first bar. When
`run_backtest` receives no `memory` mapping it runs with no memory at all and emits no `memory_written`,
which is what wave 2's scripted-stub gate run produces.

### 10.4 `Hive` (`pmx.agents.hive`, A3)

```python
REPUTATION_WINDOW_MARKETS = 50                 # a pmx.types constant (D1), re-exported here (ruling R201)

@dataclass(frozen=True, slots=True)
class HiveEntry:
    entry_id: str; kind: str; author_id: str; market_id: str | None
    written_at_ms: int; visible_from_ms: int; payload: Mapping[str, object]

class Hive(Protocol):
    def write_forecast(self, *, agent_id: str, market_id: str, bar_ms: int, prob_ppm: int,
                       resolved_at_ms: int, interval_min: int, horizon_bars: int = 0,
                       quantiles_ticks: tuple[int, ...] | None = None, price_ref_ticks: int = 0,
                       resolves_at_ms: int | None = None) -> HiveEntry: ...
        # visible_from_ms = bar_of(resolved_at_ms, interval_min) + interval_ms(interval_min); engine only.
        # Amendment C1b (17.5, ruling R160): with horizon_bars > 0 the entry is one horizon of a continuous
        # forecast, resolves_at_ms is the bar t_h the engine computed and visible_from_ms = t_h + interval_ms.
    def write_resolution(self, *, market_id: str, outcome: int, life_mean_price_bp: int,
                         resolved_at_ms: int, interval_min: int) -> HiveEntry: ...
        # visible_from_ms = bar_of(resolved_at_ms, interval_min) + interval_ms(interval_min); engine only
    def write_lesson(self, *, agent_id: str, text: str, market_ids: tuple[str, ...], bar_ms: int, interval_min: int) -> HiveEntry: ...
        # visible_from_ms = bar_ms + interval_ms; the engine writes it from Actions.lessons and Actions.notes
    def write_reputation(self, *, agent_id: str, category: str, bar_ms: int, interval_min: int, n: int, skill_micro: int, pnl_cents: int) -> HiveEntry: ...
        # visible_from_ms = bar_ms + interval_ms; engine only, recomputed in the hive phase
    def write_insight(self, *, rule: Rule, test: Mapping[str, object], fit_t1_ms: int, interval_min: int) -> HiveEntry: ...
        # amendment C1c (18.2, ruling R239): kind "insight", author_id = rule.author_id, market_id None,
        # visible_from_ms = fit_t1_ms + interval_ms(interval_min), the first bar strictly after the last bar the
        # promotion read; written by the optimizer at generation close and by L1, never by an agent
    def demote_insight(self, *, rule_id: str, bar_ms: int, interval_min: int) -> HiveEntry: ...
        # stamps demoted_at_ms on the insight; it stops firing in views from bar_ms + interval_ms
    def view(self, *, now_ms: int, agent_id: str, market_ids: Sequence[str], limits: Limits,
             live_coop: bool, blocks: Mapping[str, Mapping[str, SensorBlock]] | None = None) -> HiveView: ...
        # blocks (18.1): {market_id: {sensor: SensorBlock}} of this bar, what HiveView.insights needs to decide
        # which rules fire; None means no insight fires (a run before S1 and S2 landed). The runner fills it
        # from THIS agent's sensed observation, so an insight a diet cannot read never reaches it (R279)
    def reputation(self, *, agent_id: str, category: str | None, now_ms: int) -> ReputationView: ...
    def snapshot(self) -> dict[str, object]: ...
    def restore(self, state: Mapping[str, object]) -> None: ...

class RunHive(Hive):                             # pmx.agents.hive
    def __init__(self, *, journal: Journal, run_dir: Path, config: RunConfig,
                 snapshot: Mapping[str, object] | None = None) -> None: ...
```

`view` fills each field to its own cap and scope, and `HiveView.forecasts` has both, because an unscoped
one is either always empty (the observation's markets are all unsettled by construction) or 48 agents
times 200 markets times 300 bars, which breaches `OBSERVATION_MAX_BYTES` on every bar of every run:

| Field | Scope | Cap |
|---|---|---|
| `lessons` | every author, every category | `limits.hive_lessons`, ranked below |
| `reputations` | the agent's own open categories plus every author of a returned lesson | one row per `(agent_id, category)` |
| `resolutions` | every settled market of the run | the most recent 200 by `(-visible_from_ms, entry_id)` |
| `forecasts` | **settled markets only**, over the categories of the agent's open markets | the most recent `limits.hive_forecasts` by `(-visible_from_ms, entry_id)` |
| `prev_bar_forecasts` | every other agent, the agent's open markets, `bar_ms ==` the instrument's previous bar (`now_ms - interval_ms` on a `continuous` calendar, rulings R192 and R211) | empty unless `live_coop` |
| `insights` | the promoted, undemoted `insight` entries with `visible_from_ms <= now_ms` that `rule.readable_by(the agent's sensors)` (ruling R279) and whose rule fires at `now_ms` on one of the agent's open markets (18.2, ruling R239) | `limits.hive_insights` (`HIVE_INSIGHTS_VIEW_MAX = 50`), ranked by `(-lower_bp, rule_id)` |

`view` is a pure function of `(now_ms, agent_id, market_ids, limits, live_coop, blocks)` and of the
entries written at bars `< now_ms`; it never depends on the order agents are served in. The `insight`
entries are the one kind whose `visible_from_ms` is not one bar after their writing bar: it is one bar
after the last bar their promotion **read** (18.2), which is later than the writing bar by construction
and is the only rule under which a promoted rule can be read by agents trading bars its promotion never saw.

Reputation is computed by the engine (A3 exposes `compute_reputation(events)`) over the last
`REPUTATION_WINDOW_MARKETS` settled markets of the agent in the category: `n`, `skill_micro` (mean of
`market_brier_tw - agent_brier_tw`, `bp_ratio`-style signed rounding), `pnl_cents` (sum of
`realised_pnl_cents`). Agents never declare a reputation.

Lesson ranking in a view: by `(-author_skill_micro_in_category, -visible_from_ms, entry_id)` where
`author_skill_micro_in_category` is the author's reputation in the lesson's dominant category as of
`now_ms` (`0` when unknown), so a false lesson from an author with no or negative reputation ranks last
(the poisoning test asserts exactly that ordering). `--no-hive` makes `view` return empty tuples while
writes continue. The hive is indexed in sqlite (`runs/<run_id>/hive.sqlite`, A3) for reads by `(now_ms,
market_id)`; the sqlite file is a cache rebuilt from the journal and is never hashed.

### 10.5 The scripted families (A1, A4)

Every family is a module in `pmx.agents.families`, registered in `pmx.agents.registry.FAMILIES` with its
`GeneSpec`s (section 10.1 declares the registry's shape). Roles: `belief` families produce `prob_ppm` and a
default position rule; `overlay` families wrap an `inner` genome and transform its output; the one
`ensemble` family (`stacker`) runs its `members`. Composition depth is at most 3
(`kelly(calibrator(newsbayes))`).

**Three reading rules hold for every row and are what make the table implementable:**

1. **Every family computes its belief in ppm.** A gene suffixed `_bp` is a **threshold** compared against a
   bp quantity, never a multiplier; every multiplier is `_permille` or `_milli`. A lean is therefore
   `ppm_from_bp(move_bp) * gene_permille // 1_000`, which is why `trend`'s gene is `lean_permille` and not
   the earlier `lean_bp_per_bp` (whose name said bp per bp, whose arithmetic divided by 1 000 and whose
   result was added to a ppm: a factor of 100 away from reproducing v1's `momentum`).
2. **Every window is clamped to the available completed bars**: a family reading `k` bars back reads
   `bars[max(0, len(bars) - 1 - k)]`, exactly as frozen v1 did. A family with **fewer than two completed
   bars** states `ppm_from_bp(last_price_bp)` (which on the very first bar is
   `ppm_from_bp(first_price_bp)`, section 5.4) and holds. Without the clamp every family raises
   `IndexError` on the first bars of every market, which is guaranteed for `lookback` up to 60 or
   `range_bars` up to 90 against a seven-day minimum life; A1 pins it as a test on the first bar of a demo
   market.
3. **Every stated probability is `clamp_ppm`ed** and every division is `//` (section 1.2).

| Family | Role | Genes `name: lo..hi (step) [default]` | Rule |
|---|---|---|---|
| `follower` | belief | `shrink_permille: 0..1000 (50) [1000]`, `edge_min_bp: 0..2000 (50) [0]` | `p = 500_000 + (ppm_from_bp(last) - 500_000) * shrink // 1000`; trades only when `abs(p // 100 - last) >= edge_min_bp`. `follower(1000, 0)` is `market_follower`: it ties the market's Brier exactly and **trades nothing**, on any genome, at any bar |
| `trend` | belief | `lookback_bars: 1..60 (2) [5]`, `lean_permille: 0..2000 (50) [600]`, `confirm_bars: 1..10 (1) [1]` | `move = last - close[max(0, n - 1 - lookback)]`; `p = clamp_ppm(ppm_from_bp(last) + ppm_from_bp(move) * lean_permille // 1_000)` when the last `confirm_bars` moves share the sign, else `ppm_from_bp(last)`. `trend(5, 600, 1)` reproduces v1's `momentum` to the micro-unit |
| `revert` | belief | `half_life_bars: 1..90 (3) [10]`, `fade_permille: 0..1000 (50) [400]`, `band_bp: 0..3000 (100) [300]` | anchor = EMA of closes with the half life (integer EMA in bp); `p = clamp_ppm(ppm_from_bp(last) - ppm_from_bp(last - anchor) * fade_permille // 1_000)` when `abs(last - anchor) > band_bp`, else `ppm_from_bp(last)` |
| `timedecay` | belief | `longshot_fade_permille: 0..1000 (50) [300]`, `days_ref: 1..90 (3) [14]` | shrinks longshots toward the extreme as `close_at` nears: `scale = min(1_000, 1_000 * days_ref // max(1, days_to_close))` with `days_to_close = max(0, (close_at_ms - now_ms) // MS_PER_DAY)`; `p = clamp_ppm(ppm_from_bp(last) + (extreme - ppm_from_bp(last)) * longshot_fade_permille * scale // 1_000_000)` where `extreme` is `0` below 500_000 ppm and `PPM_ONE` above |
| `volume` | belief | `vol_lookback: 1..60 (2) [7]`, `conviction_permille: 0..2000 (50) [500]` | `ratio_permille = min(2_000, round_half_up(1_000 * bar.volume_milli, median volume over the clamped lookback))` (`0` when the median is `0`); `p = clamp_ppm(ppm_from_bp(last) + ppm_from_bp(move) * conviction_permille * ratio_permille // 1_000_000)`, so a thin move is faded and a heavy one trusted |
| `breakout` | belief | `range_bars: 2..90 (3) [20]`, `trigger_bp: 0..2000 (50) [200]`, `hold_bars: 1..60 (2) [5]` | lean in the direction of a close outside the trailing (clamped) range by more than `trigger_bp`, by `ppm_from_bp(excess_bp)`, held `hold_bars` bars |
| `newsbayes` | belief | `prior_permille: 0..1000 (50) [1000]` (weight on the market price as prior), `lexicon_id: 0..11 (1) [0]`, `weight_per_hit_milli: 0..2000 (50) [200]`, `decay_bars: 1..60 (2) [7]` | log-odds update in fixed point: `logit_milli(p) = logit_milli(prior) + sum(hits * weight_per_hit_milli)` with an integer logit table (`pmx.scoring.logit_milli`, `unlogit_ppm`, both from a 10 001-entry table built with `Decimal` at import); hits from lexicon `lexicon_id`, which is `src/pmx/lexicons/<CATEGORIES[lexicon_id]>.v1.json` (`LEXICON_COUNT = 12`, section 7.6), on as-of headlines, decayed per bar. A missing lexicon file means no hits |
| `calibrator` | overlay | `min_n: 5..100 (5) [20]`, `shrink_to_prior_permille: 0..1000 (50) [500]` | maps the inner `prob_ppm` through the memory's calibration table for `(cohort_id, horizon)` when the market has a cohort and its bin has `n >= min_n`, else for `(category, horizon)` (amendment C1c, 18.5, ruling R266: the family is **per cohort**, because a class of question systematically mispriced is a cohort-level statement): `p' = yes_rate_ppm` of the bin when `n >= min_n`, blended with the inner value by `shrink_to_prior_permille`; pools `HiveView.forecasts` (settled markets only) when own `n < min_n` and the hive is on; with `hive_insights` in the diet, a firing insight's `lift_bp` shifts the prior (ruling R240). It has **no `bins` gene**: the ledger is `CALIBRATION_BINS = 10` deciles (section 10.3) and a genome asking for 17 would have no table to read |
| `rule_follower` | belief | `min_lower_bp: 0..2000 (50) [100]`, `weight_permille: 0..2000 (50) [1000]` | amendment C1c (18.2, rulings R240 and R280): `p = clamp_ppm(ppm_from_bp(last + sum(claim.direction * (lift_bp * weight_permille // 1_000))))`, the sum over the `HiveView.insights` of the market with `lower_bp >= min_lower_bp` **and `claim.kind` in `("bias", "drift")`**, `ppm_from_bp(last)` when none fires; `required_sensors = {hive_insights}`; trades by the default position rule. `lift_bp` is the interval's `point` over `y_row`, and **every row of 18.2's measurement table is already multiplied by `direction`**, so `interval.lower > 0` makes `lift_bp` positive whatever the rule claims: without the explicit `claim.direction`, a promoted "the price is too high" rule would raise the agent's probability. The direction multiplies the **rounded** magnitude so a down-rule and the same up-rule shift by equal amounts (integer floor division of a negative product would not). A `volatility` insight is an unsigned excess move in bp and enters **no** belief; a `sizing` step may read it. A promoted rule reaches this family through the hive-insight sensor and through nothing else: no family reads the ledger files of 18.2 |
| `specialist` | overlay | `category: 0..11 (1) [0]`, `outside_mode: 0..1 (1) [0]` (`0` follow the market, `1` abstain) | inner family inside `CATEGORIES[category]`, `follower(1000, 0)` or `abstain` elsewhere |
| `kelly` | overlay | `kelly_permille: 0..1000 (50) [250]`, `max_position_pct: 1..100 (5) [20]`, `min_edge_bp: 0..2000 (50) [200]` | sizes `target_position` from the inner belief: `edge = p - ppm_from_bp(last)`; Kelly fraction of free cash on the favourable side, capped at `max_position_pct` of equity, no trade when `abs(edge) // 100 < min_edge_bp` |
| `stacker` | ensemble (coop) | `k: 1..16 (1) [5]`, `window_markets: 5..100 (5) [30]`, `extremize_permille: 1000..2000 (50) [1200]` | see below |
| `legacy` | belief | `name: 0..2 (0) [0]` | the three v1 archetypes no gene range expresses: `0` `contrarian` (`PPM_ONE - ppm_from_bp(last)`), `1` `anchor` (`ppm_from_bp(first_price_bp)`, never updated), `2` `sharp` (`ppm_from_bp(last)` plus a fixed `+/-40_000` ppm on the sign of the 3-bar move). `evolvable: False`: kept for the demo pack and excluded from mutation, crossover and immigration. Decision D-6 |

**The stacker, in full.** It instantiates and runs its own `members` (section 10.1) on the current
observation, and uses the hive **only** for the weights: `w_i = max(0, skill_micro_i) + 1_000` where
`skill_micro_i` is member `i`'s author reputation in the market's category over `window_markets` settled
markets as of `now_ms`, keeping the `k` best members by `skill_micro`. Then
`mean = sum(w_i * p_i) // sum(w_i)` and `p = clamp(500_000 + (mean - 500_000) * extremize_permille //
1_000, 10_000, 990_000)`. **When `sum(w_i) == 0` or no member has a reputation, the fallback is the
unweighted mean of the members' `p_i`**; with no members at all it states `ppm_from_bp(last_price_bp)`.
Reading the hive for the *forecasts* would divide by zero on every market the stacker is currently
forecasting, since nothing has resolved there yet; `live_coop` therefore only **adds** the other agents'
previous-bar forecasts (`HiveView.prev_bar_forecasts`) as extra members with their own reputations, and
changes no formula.

Default position rule of a belief family without a `kelly` overlay (the v1 rule, kept): `target_position
= clamp(edge_ppm * 100 // 200_000, -100, 100)` where `edge_ppm = p - ppm_from_bp(last_price_bp)`, so a
belief 20 points from the price takes the full 100 contracts, subject to cash. A family that "holds"
emits `kind = "hold"` and therefore no order at all (section 8.4).

The constructor of a roster row is 10.1's `make_agent(agent_id, genome)`, and `pmx run backtest` reads it and
`DEFAULT_ROSTER` from `pmx.agents.registry` unless `--roster-module` names another module exposing the same
two names (gate G2's scripted-stub roster, `tests/stub_roster.py`, ruling R200, and its seed-consuming
variant `tests/stub_roster_rng.py`, ruling R229).

**The default roster** (`pmx.agents.registry.DEFAULT_ROSTER`) is the eight v1 archetypes as eight literal
genomes, and `tests/test_agents_families.py` asserts each one reproduces the frozen v1 belief on the
migrated demo pack to the micro-unit:

| v1 name | genome |
|---|---|
| `market_follower` | `follower(shrink_permille=1000, edge_min_bp=0)` |
| `calibrated` | `follower(shrink_permille=880, edge_min_bp=0)` |
| `mean_revert` | `follower(shrink_permille=600, edge_min_bp=0)` |
| `stubborn` | `follower(shrink_permille=0, edge_min_bp=0)`, which is exactly `500_000` ppm forever |
| `momentum` | `trend(lookback_bars=5, lean_permille=600, confirm_bars=1)` |
| `contrarian` | `legacy(name=0)` |
| `anchor` | `legacy(name=1)` |
| `sharp` | `legacy(name=2)` |

Only three archetypes need `legacy`, and they are exactly the three no gene expresses: `contrarian` would
need a negative `shrink_permille`, `anchor` reads the first price rather than the last, and `sharp`'s lean
is a fixed `+/-40_000` ppm on the sign of a move, not proportional to it as `trend`'s is. `stubborn` is
`follower(0, 0)` and `momentum` is `trend`, so neither is legacy: the earlier draft listed both and was
wrong, and it also retracted itself mid-paragraph and delegated the roster to `registry.py`, which is not
something a contract may do. Decision D-6, corrected.

`ensembles.py` (A4) ships `top_k_extremized_mean(k, extremize_permille)` as a fixed (non-evolving)
stacker genome present in every population, and the `live_coop` flag: when on, `HiveView.prev_bar_forecasts`
carries the previous bar's forecasts of every other agent and the stacker may weight them as extra
members; the flag is in `RunConfig`, so the journal hash changes when it is on (the A4 test).

---

## 11. The gateway and the LLM agents

### 11.1 Port of `pxe.gateway`

`pmx.gateway` (A5) ports Exchange's `protocol.py`, `budget.py`, `claude_cli.py`, `scripted.py`,
`prompt.py` with these renames and no other design change: `collect_actions -> collect_replies`,
`acollect_actions -> acollect_replies`, `tick -> bar_ms`, `MatchConfig -> RunConfig`, `match ->
run`, `tournament -> evolution` in budget scopes, `pxe.* -> pmx.*` imports, `HarnessConfig ->
LlmSeatConfig` (section 11.4), `reset_agents` dropped (the runner resets agents itself, section 10.2).
**`AgentReply` and the `Gateway` protocol are declared in `pmx.types` (D1), not here**, and
`pmx.gateway.protocol` re-exports them under the same names. The reason is rule 1 of
`tests/test_architecture.py`: `agents/protocol.py` must annotate `receive(self, reply: AgentReply)` and
`engine/runner.py` must annotate `gateway: Gateway | None`, and neither file may name `pmx.gateway` in any
import, including one guarded by `if TYPE_CHECKING`. Both packages import the two names from `pmx.types`,
the rule stays literal, and no `# noqa` is needed anywhere.

Verbatim: `BaseGateway`'s `asyncio.run` bridge, semaphore, per-call timeout, the
fallback path, `BudgetTracker` with its three scopes and pre-call checks, `build_cli_argv` (same argv,
same `--json-schema`, never `--bare`), `parse_cli_stdout`, `write_llm_trace`, the retry-inside-timeout
division, the `ScriptedGateway` shape (here keyed by canned replies for tests, since scripted agents do
not go through the gateway in pmx).

```python
@dataclass(frozen=True, slots=True)
class AgentReply:
    agent_id: str
    raw: Mapping[str, object] | None       # the parsed JSON payload in the actions.v2 shape, or None
    raw_text: str | None                   # trace only
    source: str                            # "llm" | "fallback"
    error: str | None                      # a RejectReason value on failure
    cost_usd: float = 0.0                  # trace only; a legal float site (preamble rule 3)
    latency_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cached_input_tokens: int = 0
    attempts: int = 1

class Gateway(Protocol):
    def collect_replies(self, *, bar_ms: int, observations: Sequence[Observation], config: RunConfig) -> tuple[AgentReply, ...]: ...
    async def acollect_replies(self, *, bar_ms: int, observations: Sequence[Observation], config: RunConfig) -> tuple[AgentReply, ...]: ...
    def close(self) -> None: ...

class BaseGateway(Gateway):
    def __init__(self, *, gateway_config: GatewayConfig | None = None, budget: BudgetTracker | None = None) -> None: ...
    async def acall_agent(self, *, agent_id: str, observation: Observation, bar_ms: int) -> AgentReply: ...

@dataclass(frozen=True, slots=True)
class GatewayConfig:
    timeout_s: float = 120.0; retries: int = 1; max_parallel_calls: int = 4
    max_budget_usd_per_call: float = 0.10; max_budget_usd_per_run: float = 5.0; max_budget_usd_per_evolution: float = 50.0
    max_input_tokens_per_call: int = 60_000; max_output_tokens_per_call: int = 4_000; max_tokens_per_run: int = 0   # 0 = unlimited

class BudgetTracker:
    def __init__(self, config: GatewayConfig) -> None
    def check(self, *, scope: str, amount_usd: float) -> None                       # "call" | "run" | "evolution"
    def check_tokens(self, *, input_tokens: int, output_tokens: int, agent_id: str | None = None, bar_ms: int | None = None) -> None
    def note_bar(self, bar_ms: int) -> None
    def record(self, reply: AgentReply, *, bar_ms: int | None = None) -> None
    def reset_run(self) -> None
    def spent_usd(self, scope: str = "run") -> float
    def remaining_usd(self, scope: str = "run") -> float
    def spent_tokens(self, scope: str = "run") -> tuple[int, int]
    def bar_tokens(self, agent_id: str, bar_ms: int) -> tuple[int, int]
    def calls(self, scope: str = "run") -> int

class ClaudeCliGateway(BaseGateway):
    def __init__(self, *, seats: Mapping[str, LlmSeatConfig], gateway_config: GatewayConfig, budget: BudgetTracker, trace_path: Path | None = None) -> None
class ScriptedGateway(BaseGateway):
    def __init__(self, *, replies: Callable[[str, Observation], Mapping[str, object] | None]) -> None
        """A callable that returns the raw payload (or None for a fallback) for (agent_id, observation).
        Every offline test of an LLM path uses it; it spends nothing and reads no clock."""
```

The four boundary rules hold verbatim: the gateway returns replies, never `Actions`; `raw` is a mapping
in the `actions.v2` shape or `None`; the gateway never validates semantics (the runner does, section
8.4); `raw_text`, `cost_usd`, `latency_ms`, tokens and `attempts` never reach the journal.

The float sites of this section are the ones the preamble's rule 3 names: `AgentReply.cost_usd`, and
`GatewayConfig.timeout_s`, `max_budget_usd_per_call`, `max_budget_usd_per_run`,
`max_budget_usd_per_evolution` with `BudgetTracker`'s `check`, `spent_usd` and `remaining_usd`. None of
them is journaled or hashed. Every other number in this section is an integer.

### 11.2 The trace

`runs/<run_id>/llm_trace.jsonl`, one line per call, written only by `claude_cli.py`:
`bar_ms, agent_id, seat_key, model, prompt_template_version, ok, error, attempts, cost_usd, latency_ms,
input_tokens, output_tokens, cache_creation_input_tokens, cache_read_input_tokens,
estimated_input_tokens, raw_text, rationale`. Outside every hash. `pmx replay` never reads it.

### 11.3 One call per agent per bar

An LLM agent makes exactly one provider call per bar, covering every open market, its pending post-mortems
(section 8.2, learn) and its research request. The observation is rendered as compact text by
`pmx.llm.forecaster.render_observation(obs, *, dials)`; the reply is validated against
`actions.v2.json` (section 7.13) by the runner. A call refused by the budget, timed out, or malformed after the
retries becomes `reply_received(source="fallback")`: forecasts carried, `hold` everywhere, no lessons.
`BudgetTracker.bar_tokens` exists so the test can assert per bar equals per call.

### 11.4 LLM seats and the prompt genome

```python
@dataclass(frozen=True, slots=True)
class ModelSpec:
    model: str                             # "claude-haiku-4-5" | "claude-sonnet-5" | "claude-fable-5-1" | ...
    knowledge_cutoff_ms: int               # declared in configs/models.json (A5 owns the file)

DIALS = ("base_rate_discipline", "news_weight", "contrarian_appetite", "kelly_fraction",
         "memory_reliance", "hive_reliance", "verbosity")
DIAL_LEVELS = 5                            # each dial is an int in 0..4 selecting a text block

@dataclass(frozen=True, slots=True)
class PromptGenome:
    frame_version: str                     # the fixed system frame, "frame.v1", from src/pmx/llm/prompts/frame.v1.md
    dials: tuple[tuple[str, int], ...]     # sorted by dial name, values 0..4
    def to_dict(self) -> dict[str, object]: ...

@dataclass(frozen=True, slots=True)
class LlmSeatConfig:
    agent_id: str; model: ModelSpec; prompt: PromptGenome
    @property
    def seat_key(self) -> str: ...         # f"{model.model}@{frame_version}+{genome_hash[:8]}"
```

`pmx.llm.forecaster.LlmForecaster` is **the one LLM agent implementation**. It is constructed by its
caller (the CLI, or the optimizer) from an `LlmSeatConfig`, it reports `kind = "llm"`, `family = "llm"`
(a name reserved by the contract), `model` and `knowledge_cutoff_ms` (section 10.2), and it is passed into
`run_backtest`'s roster like any other agent. It is registered in **no** `FAMILIES` entry: a `FamilySpec`
carries a `make` callable, and a `FAMILIES` row for it would make `agents/registry.py` import `pmx.llm`,
which rule 1 forbids. Its prompt genome mutates through `evolution.prompt_mutation` and section 12.9.

Dial text blocks live in `src/pmx/llm/prompts/<dial>.<level>.md`; a mutation moves one dial by one level
(`evolution.prompt_mutation`) or, through section 12.9's pipeline, proposes a whole new dial vector. The
system prompt is `frame + the seven selected blocks + the output discipline`, a pure function of the seat
config; the user prompt is the rendered observation. Nothing of it is journaled; the genome (dials) is.

### 11.5 Contamination

A market is `clean` for a model iff `created_at_ms > knowledge_cutoff_ms`. `pmx audit contamination
--model X` (A6) asks the model, through the gateway with a `ContaminationPrompt` (question only, three
paraphrases from `src/pmx/lexicons/paraphrases.v1.json`, temperature `0`, `--max-budget-usd` cap), for the
outcome; a market where at least two of three answers name the true outcome with stated confidence
`>= CONTAMINATION_CONFIDENCE_PPM = 800_000` is tagged `contaminated:<model>` in
`data/datasets/<name>/contamination.json` (outside the dataset hash, keyed by `dataset_hash`). LLM
leaderboard rows are computed on `clean and not contaminated` markets and carry `n_clean`. The scripted
population never reads this file.

**The audit is coarse and says so** (decision D-R6, ruling R252). Three paraphrases at temperature zero
detect blatant recall of an outcome and nothing subtler (a model that knows the outcome and answers the
paraphrase with a hedge passes), so every LLM leaderboard row carries `contamination_audit:coarse` in
`LeaderboardRow.labels` (12.10), and **an LLM result never enters a claim before the live book replicates
it**: a claim on an LLM genome computes and records its four parts, and its `verdict` reads
`awaiting_live_replication` until `live/` holds at least `LIVE_REPLICATION_MIN_RESOLVED = 100` resolved
forecasts of that `genome_hash` and `model` whose `skill_lb_micro` is positive; only then may it read
`beats_market` (12.8). The number is decision D-R11's and is a default.

**The file is outside the dataset hash, so it is inside the run's.** `contamination.json` decides which
sealed markets an LLM genome is scored on, which is a result-changing input: `RunConfig.contamination_hash`
(section 8.1) carries `sha256` of its bytes, `run_started` journals it, `claims/<claim_id>.json` records
it with `n_clean` and with `clean_market_ids` verbatim, and `run_backtest` and `claim` recompute the hash
and raise `DatasetHashMismatchError` on a mismatch. Without that, an LLM claim is not reproducible from
`(dataset_hash, config, seed)` and can be improved after the fact by editing an unhashed local file to
drop the markets the agent lost.

**The hook the leaderboard calls is a pure function, so `pmx.metrics` never imports `pmx.llm`:**

```python
# pmx.llm.contamination (A6)
def load_contamination(dataset_path: Path, dataset_hash: str, model: str) -> frozenset[str]: ...
def is_clean(meta: MarketMeta, *, knowledge_cutoff_ms: int | None,
             contaminated_ids: frozenset[str]) -> bool: ...
    # True iff knowledge_cutoff_ms is None, or (meta.created_at_ms > knowledge_cutoff_ms
    # and meta.id not in contaminated_ids)
def audit(*, gateway: Gateway, metas: Sequence[MarketMeta], model: ModelSpec,
          dataset_path: Path, dataset_hash: str) -> Mapping[str, frozenset[str]]: ...

# pmx.metrics.leaderboard (E5): the set arrives from the caller, never from an import
def build(projection: RunProjection, *,
          contaminated: Mapping[str, frozenset[str]] | None = None) -> tuple[LeaderboardRow, ...]: ...
    # contaminated is keyed by agent_id (ruling R221): A6's audit maps its per-model verdict onto the run's
    # seats before handing it over; the caller owns the mapping, never the leaderboard
```

---

## 12. Scoring, statistics, selection, the bar, folds and claims

Everything here is a projection of the journal (`pmx.metrics.projection.project(events) -> RunProjection`)
and reads no engine state, no dataset, no agent and no gateway (section 9.5's replay guarantee; the
`market_listed` and `market_priced` events of section 9.2 are what make it possible). All outputs are
integers.

**Every ratio in this section is `0` when its denominator is `0`**, and a bin, bucket or slice with
`n == 0` reports `n: 0` with every other field `0`. This is not a courtesy: nine of ten reliability bins
are empty for `market_follower`, `sum(requested_size)` is `0` for every agent that never orders,
`n_markets_open` is `0` for an agent that saw no market, and `round_half_up` is only defined for a
positive denominator (section 1.2). E5's test asserts that the projection of a run whose roster is
`follower(1000, 0)` alone produces a complete leaderboard row with `fill_ratio_ppm == 0`,
`turnover_ppm == 0`, `category_coverage_ppm == 0` and `skill.point == 0`, rather than raising
`ZeroDivisionError`.

### 12.1 Forecast scores (E3, `pmx.scoring`)

For an agent `a` on a market `m` with forecast bars `t_1 < ... < t_n` (every bar where `open(m, t)` held
and a `forecast_recorded` exists, carried or not) and outcome `y`:

- `b_i = brier_micro(p_i, y)`; `w_i = t_{i+1} - t_i` for `i < n`, `w_n = interval_ms` (the last bar's own
  length), so on a regular grid every weight is `interval_ms` and the weighted mean **equals the plain
  mean exactly** (E3 asserts the identity). `brier_tw_micro = round_half_up(sum(b_i * w_i), sum(w_i))`.
- The market's own `market_brier_tw_micro` uses `p_i = ppm_from_bp(market_priced.last_close_bp at t_i)`
  on the same bars, which is the close of the last completed bar at `t_i` and, **on a market's first bar
  where no bar is completed, `market.first_price_bp`** (section 5.4). That is exactly what
  `follower(1000, 0)` states on every bar including the first, so the identity
  `skill(market_follower) == 0` holds by construction rather than by luck.
- `skill_micro(a, m) = market_brier_tw_micro - brier_tw_micro(a)`; `skill_vs_5000_micro` likewise
  against the constant `500_000`.
- Horizon buckets: `b_i` grouped by `days_to_close = (close_at_ms - t_i) // MS_PER_DAY` into `30d`
  (`>= 30`), `7d` (`[7, 30)`), `2d` (`[2, 7)`), `0d` (**`< 2`**); each bucket reports its time-weighted
  Brier and `n_bars`. The last bucket is `< 2` and not `[0, 2)` because section 5.3 keeps a market open
  between `close_at_ms` and `resolved_at_ms`, where `days_to_close` is negative: every settlement-lag bar
  falls in `0d`, and `HORIZON_BUCKETS` (section 10.3) says the same.
- Log score: `log_micronats = neg_ln_micronats(clamp(p_i, LOG_CLAMP_LO_PPM, LOG_CLAMP_HI_PPM))` when
  `y == 1` and `neg_ln_micronats(clamp(PPM_ONE - p_i, LOG_CLAMP_LO_PPM, LOG_CLAMP_HI_PPM))` when `y == 0`,
  time-weighted like Brier.
- PMV at horizon `h` days: `pmv_bp(t_i) = sign(p_i - ppm_from_bp(price_i)) * (price_{t_i + h} - price_i)`
  using the close at the first bar `>= t_i + h * MS_PER_DAY` that is still `< bar_of(resolved_at_ms)`;
  bars with no such future bar are skipped; reported as the mean over the remaining bars for
  `h in (1, 7)`, and `0` when every bar was skipped.
- Log-odds, for `newsbayes` (10.3) and `features.v1`'s `logit_last_milli` (16.5): `logit_milli(prob_ppm) -> int`
  and `unlogit_ppm(logit_milli) -> int` (E3, ruling R217). The table has 10 001 entries indexed by a probability
  in basis points, built in `Decimal` at precision 40 and exactly antisymmetric; the index rounds to the nearest
  basis point with a tie toward even odds; `unlogit_ppm` returns a probability in `[100, 999_900]` ppm and is
  antisymmetric, monotone and idempotent; the round trip is within `LOGIT_ROUND_TRIP_PPM_MAX = 250` ppm.

Everything above is the **binary** row of section 17.5 (amendment C1b, rulings R157 to R159). A
continuous instrument has no outcome `y`: a forecast at `t` is a per-horizon `up_probability_ppm` with
optional quantiles, scored at the horizon by the directional Brier (`directional_brier_micro`, with a
flat return scoring half each way) and the pinball loss (`pinball_micro`, relative to the reference
price), against the random-walk baseline (`500_000` and the current price as every quantile), whose
skill is `0` by construction exactly as `market_follower`'s is here. The horizon buckets read `h<n>` per
declared horizon and the log score is not defined (`0`, `n: 0`).

### 12.2 Calibration (E3, `pmx.metrics.calibration`; imports nothing from execution)

Over every `(agent, market, bar)` forecast of a run: `CALIBRATION_BINS = 10` bins by
`prob_ppm // 100_000` (the top bin takes `PPM_ONE`); per bin `n`, `mean_prob_ppm`,
`yes_rate_ppm = round_half_up(PPM_ONE * n_yes, n)`;
`ece_ppm = sum(n_bin * abs(mean_prob - yes_rate)) // n_total`; `sharpness_ppm = sum(n_bin *
abs(mean_prob - 500_000)) // n_total`. An empty bin reports `n: 0, mean_prob_ppm: 0, yes_rate_ppm: 0` and
a slice with `n_total == 0` reports `ece_ppm: 0, sharpness_ppm: 0` (the preamble's rule; nine of ten bins
are empty for `market_follower` on a single market). Time-weighting is not applied to calibration (bins
count forecasts), which is stated so nobody "fixes" it. On a continuous kind the same table bins
`up_probability_ppm` per `(kind, horizon)` slice with `n_yes_x2` counting an up as `2` and a flat
realisation as `1` (amendment C1b, section 17.5, ruling R161); nothing is pooled across kinds or horizons.
`CalibrationBinView` carries `n_yes_x2` as a defaulted field (`2 * n_yes` on a binary slice) and every
consumer computes `yes_rate_ppm` from it over `2 * n`, one spelling in `pmx.metrics.calibration` (ruling
R194), so a tie is never dropped and no ratio is off by two. `AgentResult` carries the two numbers as `ece_ppm` and
`sharpness_ppm` over the agent's own slice (ruling R221), so 12.10's column is read and never recomputed;
`CalibrationBinView` carries no `mean_prob_ppm`, because 8.3 hands the view to an agent and a per-bin mean
probability is a second channel. Every consumer imports `CalibrationBinView` from `pmx.types` and no module
re-exports it (ruling R217). `project()` builds one calibration entry per resolved continuous horizon through
`continuous_entry` keyed `(kind, f"h{horizon_bars}", bin)` (declared by ruling R217, wired by E5 in the next
lot: today the projection calls `binary_entry` only), so a continuous row's `ece_ppm` is its own ledger's.

### 12.3 Trading metrics (E5, `pmx.metrics.performance`)

Per agent per run, from `filled`, `fee_charged`, `settlement_applied`, `equity_marked`: `pnl_cents =
final_cash - bankroll` (equals `sum(realised_pnl_cents)` at run end); `return_bp = bp_ratio(pnl_cents,
bankroll_cents)`; `max_drawdown_bp = min(drawdown_bp)`; `sharpe_milli = milli_ratio(mean_bp, sd_bp)` over
daily equity changes in bp of bankroll with `sd_bp = isqrt(sum((x - mean)^2) // (n - 1))` (integer
square root, `0` for `n < 2`, ratio `0` when `sd_bp == 0`); `turnover_cents = sum(abs(cash_delta) over
fills)`; `fill_ratio_ppm = round_half_up(PPM_ONE * sum(filled_size), sum(requested_size))`;
`fees_paid_cents`; `ruined: bool`; `n_markets_traded` (markets with at least one `filled` event of
`filled_size >= 1`); `n_markets_open` (section 12.5). Amendment C1b (section 17.3, ruling R163): `pnl_cents`
includes every `cash_event_applied.cash_delta_cents` (funding, dividends, borrow fees) and the fees of
every event fill, `turnover_cents` includes event fills, `n_cash_events` counts the agent's
`cash_event_applied` rows, and `exposure_by_kind` is the mean over bars of the absolute marked notional
per kind in cents, sorted by kind.

Two abstention numbers, because one was gameable by silence:

- `abstention_ppm` is the share of `(agent, market, bar)` decisions where the agent **ended the bar with
  `position == 0` and placed no order on that market**. This is the column the archive axis of section
  12.5 and the leaderboard of section 12.10 use.
- `explicit_abstain_ppm` is the share with `kind == "abstain"`, reported beside it.

**Capacity** (decision D-R10, ruling R255; `pmx.metrics.capacity`, O4). Kalshi's fee of seven percent of
`p(1-p)` and thin books make most micro-edges untradeable, so a PnL failure will be liquidity and not
skill, and a claim has to say at what size. `capacity_cents(fills, bars, config, schedule) ->
CapacityReport` re-prices every fill of a run at each scale of `CAPACITY_SCALE_GRID_PERMILLE = (1000,
2000, 5000, 10000, 20000, 50000, 100000)` (the requested size times the scale) through `historical`'s own
cap, slippage and fee functions of `pmx.engine.liquidity` on the same bars (architecture rule 9 holds: no
fill price is computed elsewhere). **The formula, in integers** (ruling R292), because "the return" and
"half" are ambiguous on a signed quantity and the grid's first entry is the unit scale itself:

```python
notional_cents(s) = sum(abs(cash_delta_cents) over the fills re-priced at scale s)   # never the bankroll
ret_bp(s)         = bp_ratio(pnl_after_fees_cents(s), notional_cents(s))             # against the notional at s
# halving_scale_permille, in one of exactly three states:
#   ret_bp(1000) <= 0  ->  halving_scale_permille = 0 and capacity_cents = 0
#                          (an edge that does not survive its own unit scale has no capacity; the metric
#                           does NOT report the unit notional as a capacity, which the earlier wording did
#                           whenever the unit return was negative)
#   else the smallest s > 1000 in CAPACITY_SCALE_GRID_PERMILLE with ret_bp(s) * 2 <= ret_bp(1000):
#                          capacity_cents = notional_cents(s_prev), s_prev the grid scale below it
#                          (the largest tested notional that KEPT more than half the unit return; the
#                           notional at the halving scale is a size the edge did not survive)
#   no such s          ->  halving_scale_permille = -1 and capacity_cents = notional_cents(grid_max_permille)
#                          with grid_max_permille reported: the grid ran out before the edge did
```

The report carries the three numbers **per market and in aggregate** (12.8's `capacity` block), and the
**aggregate** is computed on the aggregate curve (one `ret_bp(s)` over every fill of the run), never as a
function of the per-market halving scales. No interpolation, stated so nobody smooths it.
It needs the dataset's bars, so it is computed at claim time (12.8) and never by the journal projection;
every claim reports `capacity` beside `pnl`. Every cohort row of 12.10 and 12.8 carries its `n` beside
every number, so a comparison across cohorts is never read without its size (decision D-S7).

The earlier definition measured only the keyword, and section 8.4 treats a missing market as `hold` while
`follower` with `edge_min_bp > 0` never trades: the agent that is silent on every market reported
`abstention_ppm = 0`, so the one column meant to expose silence read zero for the most silent agent, and
two behaviourally identical agents landed in different MAP-Elites cells.

### 12.4 Statistics (E4, `pmx.metrics.stats`; the only numpy module)

Inputs are per-market integer vectors from the projection; outputs are integers; numpy is seeded from
`stats.bootstrap` / `stats.permutation` (section 6).

```python
BOOTSTRAP_RESAMPLES = 10_000
PERMUTATIONS = 1_000
PERMUTATION_INNER_RESAMPLES = 200
ALPHA_PPM = 50_000                          # one-sided 95 percent lower bounds

def block_key(market: MarketMeta, *, cluster_id: str | None = None) -> str
    # cluster_id if not None, else market.event_key if not None, else f"w{iso_year}-{iso_week:02d}" of resolved_at_ms;
    # on a continuous (instrument, week) row the week is the cell's own (17.6, ruling R186), not the meta's
    # MarketMeta is section 7.2's leak-free projection; the projection carries block_key per (agent, market).
    # The keyword-only cluster_id is amendment C1's (ruling R118, applied here rather than deferred): two
    # venues' markets on one event are one block, not two independent draws. E4 ships the argument in wave 2
    # and R1b fills it in wave 7. This is the engine's own use of the grouping, in the statistics, where
    # hindsight is allowed and no agent is looking (section 16.3).
def iso_week_key(t_ms: int) -> str
    # the one spelling of f"w{iso_year}-{iso_week:02d}" (ruling R219): block_key's week branch calls it and
    # PerMarket.unit_key is f"{market_id}/{iso_week_key(cell_ms)}" on a continuous cell
def bootstrap_lower_bound(values: Sequence[int], blocks: Sequence[str], *, rng: RngTree, alpha_ppm: int = ALPHA_PPM,
                          resamples: int = BOOTSTRAP_RESAMPLES) -> Interval
    # Interval(point: int, lower: int, upper: int, sd: int, n: int, n_blocks: int, resamples: int); to_dict() renders
    # exactly those keys, and opportunity.v1.json and model_card.v1.json carry MAPPED fields (payoff_point_cents,
    # payoff_lb_cents, null_lb_cents, skill_lb_micro), never an embedded to_dict() (ruling R219)
    # resample n_blocks blocks with replacement, mean of the concatenated values, empirical quantile at
    # floor(alpha * B) (lower) and ceil((1 - alpha) * B) - 1 (upper); every field rounded half away from zero.
    # Fewer than two blocks (an empty `values` included) has no bootstrap: return
    # Interval(point=mean(values) or 0, lower=point, upper=point, sd=0, n=len(values), n_blocks, resamples)
def paired_lower_bound(agent: Sequence[int], baseline: Sequence[int], blocks: Sequence[str], *, rng: RngTree,
                       alpha_ppm: int = ALPHA_PPM, resamples: int = BOOTSTRAP_RESAMPLES) -> Interval   # bootstrap of (agent - baseline), R219
def deflated_lower_bound(interval: Interval, *, candidates: int) -> int
    # Bonferroni on the family-wise count: lower_defl = point - z(1 - alpha / K) * sd, K = max(1, candidates),
    # z from statistics.NormalDist().inv_cdf, the product rounded half away from zero to an integer.
    # The undeflated bound is the empirical quantile; the deflated one is the normal approximation because
    # an empirical quantile at alpha / K needs B >= 20 K / alpha resamples, which is out of reach for K in the thousands.
    # Defined at ALPHA_PPM only: bootstrap_lower_bound's alpha_ppm is for reporting and is never deflated (ruling R219).
def benjamini_hochberg(p_values_ppm: Sequence[int], *, q_ppm: int = FDR_Q_PPM) -> tuple[bool, ...]
    # Amendment C1c (18.2, decision D-R8, ruling R238): false discovery rate control WITHIN a pre-registered
    # hypothesis family. FDR_Q_PPM = 50_000. With m = len(p_values_ppm) and p_(1) <= ... <= p_(m) the sorted
    # values, k is the largest index with p_(k) * m <= k * q_ppm (integers, no division); the result marks True
    # every position whose p-value is <= p_(k), and no position when no such k exists. Deflation of a CLAIM stays
    # deflated_lower_bound above (Bonferroni on K); this function governs rule promotion only and never a claim.
    # E4's name, added by S2 by the agreement recorded in section 13.
def rule_permutation_p_ppm(y_rows: Sequence[int], fired: Sequence[bool], blocks: Sequence[str],
                           *, rng: RngTree, permutations: int) -> int
    # Amendment C1c (18.2, decision D-R8, rulings R238 and R282): THE RULE PATH'S NULL, and the only null
    # a rule's FDR step calls. The three sequences are aligned, one entry per row of the replicate fold in
    # the rule's scope: y_rows the row's realised measurement (18.2's table), fired whether the rule's
    # condition held there, blocks the row's block_key. For each permutation, shuffle `fired` WITHIN each
    # block (so every block keeps the number of rows the rule matched in it) from `stats.permutation` of the
    # handed tree, and recompute the mean of y_rows over the matched rows: the SAME statistic the promotion
    # criterion tests, so a rule cannot pass one gate and fail the other for a reason nobody can read.
    # Returns p_value_ppm = round_half_up(PPM_ONE * (b + 1), permutations + 1), b the permutations whose
    # mean reached the observed one: the (b + 1) / (B + 1) estimator, so a permutation p-value is NEVER 0
    # and is comparable against a Benjamini-Hochberg threshold of k * q / m. No inner bootstrap: this is a
    # mean over rows, not a per-market lower bound, so raising `permutations` with the family size (18.2
    # step 3) costs one pass per shuffle.
def permutation_null(forecasts: Mapping[str, Sequence[tuple[int, int]]], market_prices: Mapping[str, Sequence[int]],
                     outcomes: Sequence[int], weights: Mapping[str, Sequence[int]], blocks: Sequence[str],
                     *, rng: RngTree, permutations: int = PERMUTATIONS, inner: int = PERMUTATION_INNER_RESAMPLES,
                     realised_signs: Mapping[str, Sequence[int]] | None = None,
                     bar_keys: Mapping[str, Sequence[str]] | None = None) -> NullResult
    # NullResult(null_lb_micro: int, p_value_ppm: int, permutations: int); to_dict() renders exactly those keys
    # forecasts: (bar_ms, prob_ppm) pairs in bar order (up_probability_ppm at the claim's horizon on a continuous cell);
    # market_prices: the market's own prob_ppm on the same bars; weights: section 12.1's w_i in ms, which is
    # bar_weights_ms of the same bars and nothing else (asserted against scoring.skill_micro); blocks: one block key
    # per unit; outcomes and blocks are aligned with sorted(forecasts), the one order the module reads; a continuous
    # call passes empty market_prices and weights (ruling R219). The shuffles draw from stats.permutation and the
    # inner resamples from stats.bootstrap, each from the handed RngTree: the split fixes every published
    # null_lb_micro. The exchangeability group is (block, bar key); on a clustered instrument the block is the
    # cluster, deliberately coarser (ruling R219).
    # for each permutation: shuffle outcomes across markets, recompute skill per market (forecasts and prices fixed),
    # take the block-bootstrap lower bound with `inner` resamples; null_lb_micro = 95th percentile of those lower bounds;
    # p_value_ppm = share of permutations whose mean skill >= the observed mean skill. This is the CLAIM
    # path's p-value and is reported beside a Bonferroni-deflated bound; part 4 of the four-part bar (12.6)
    # thresholds null_lb_micro and never this number, so its 1 / permutations resolution decides nothing.
    # A rule's p-value is rule_permutation_p_ppm above and never this function (ruling R282): its
    # market_prices, outcomes and bar_weights_ms arguments have no meaning for a rule's matched
    # (market, bar) rows, and a Brier skill against the market would fail a rule whose direction is right
    # and whose magnitude_bp is off by half, which 18.2 calls a useful rule.
    # Amendment C1b (17.6, ruling R190), keyword-only: on a continuous kind `outcomes` is empty, `realised_signs`
    # carries one realised_sign per forecast of each (instrument, week) cell and `bar_keys` the f"{t}/{h}" key of
    # each forecast; a permutation shuffles realised_sign among the forecasts of the same week that share a key
    # (same forecast bar, same horizon, different instruments), leaves unmatched forecasts in place and
    # recomputes the per-cell directional skill. price_realised_ticks is never shuffled.
```

E4's tests: a synthetic agent with known skill gets an interval containing it; the shuffled null centres on
zero; `deflated_lower_bound` is strictly decreasing in `candidates` on an interval with `sd > 0` and invariant
on the degenerate interval of ruling R68 (R219).

### 12.5 Behavioural descriptors and the archive grid (E5 computes, O2 bins)

| Descriptor | Definition | Archive axis | Bins |
|---|---|---|---|
| `turnover_ppm` | `round_half_up(PPM_ONE * turnover_cents, bankroll_cents * n_markets_open)` | yes | `[0, 250_000)`, `[250_000, 1_000_000)`, `[1_000_000, 4_000_000)`, `[4_000_000, inf)` |
| `contrarian_bp` | mean over forecasts of `(prob_ppm // 100 - last_price_bp)`, `bp_ratio` rounding | yes | `(-inf, -300)`, `[-300, 0)`, `[0, 300)`, `[300, inf)` |
| `abstention_ppm` | section 12.3 | yes | `[0, 100_000)`, `[100_000, 500_000)`, `[500_000, 1_000_000]` |
| `holding_horizon_bars` | mean bars between opening and flattening a leg | reported | |
| `category_coverage_ppm` | `round_half_up(PPM_ONE * categories traded, categories open)` | reported | |
| `diet_class` | amendment C1c (18.1, rulings R235 and R289): `0` when the diet carries no news sensor and no hive sensor, `1` when it carries at least one news sensor (`wiki_daily`, `comments`, `hn`, `gdelt_recent`, `filings`, `macro_releases`, `wiki_asof`) and no hive sensor, `2` when it carries `hive_insights` or `hive_reputation`. The projection reads the diet off **`observation_built.sensors` of the agent's first observation of the run**, which equals `Genome.sensors` by construction (18.1), because `pmx replay` may read nothing but `journal.jsonl` (9.5) and a journal carries no `Genome`. A journal written before ruling R274's lot carries no `sensors`, and the projection then reads the full catalogue, which is exactly what such a run ran under (the runner passed `None` to every agent), so `diet_class = 2` and no unknown state is needed | yes | `{0}`, `{1}`, `{2}` |

`n_markets_open` is **the number of distinct markets that appeared in at least one of the agent's
observations during the run** (equivalently, that carry at least one `forecast_recorded` for it), and it is
a field of `AgentResult` (section 12.11) so E5 and O2 read the same integer rather than two readings of the
same phrase. "categories open" is the number of distinct `market_listed.category` values over those
markets, "categories traded" the number over the markets with at least one fill. `contrarian_bp` is the
mean over the agent's forecast bars of `(prob_ppm // 100 - market_priced.last_close_bp)` with `bp_ratio`
rounding. Each of the three is `0` when its denominator is `0`.

The six of them travel together as one frozen dataclass, which E5 fills and O2 bins:

```python
@dataclass(frozen=True, slots=True)
class Descriptors:
    turnover_ppm: int; contrarian_bp: int; abstention_ppm: int
    holding_horizon_bars: int; category_coverage_ppm: int
    diet_class: int = 0                             # amendment C1c (18.1, ruling R235); defaulted so a v2 payload reads
    def to_dict(self) -> dict[str, int]: ...        # the candidate_scored.descriptors payload of 9.4
```

`ARCHIVE_CELLS = 4 * 4 * 3 * 3 = 144`; `cell_key = f"t{i}-c{j}-a{k}-d{l}"`. AC-6's "at least 40 percent" is
read against `ARCHIVE_CELLS_REACHABLE = 48 * (the distinct diet_class values among the genomes scored at
the engine tier)` and not against 144 (ruling R297, 18.1): 20 cells while the roster's diets all sit in
one class, 58 once all three are populated, both numbers reported. Decision D-7 recorded
the choice of three axes and is amended by amendment C1c (ruling R235): PRD v5 1.2 asks the archive to keep
a volume-reader, a news-reader and a hive-reader alive even when one dominates, and a descriptor that is
reported but not binned keeps nothing alive.

### 12.6 The selection objective and the beat-the-market bar

Objective (O1, on the **training** fold of a generation): the tuple `(skill_lb_micro, pnl_lb_cents)`,
both 95 percent block-bootstrap lower bounds of the per-market means, compared lexicographically,
descending; ties by `agent_id`. A `ruined` agent ranks below every non-ruined one. Patience is measured on
`best_validation_lb_micro`, the best validation-fold `skill_lb_micro` of the population, **at the engine
tier**.

**The evolutionary loop is a generator, not a certifier** (decision D-R7, ruling R253). One hundred and
eleven training markets cannot detect a Brier edge of 0.005 when the market-level standard deviation is
near 0.15, and 48 by 30 evaluations make the deflated bound of 12.4 unreachable on them; the objective
above **selects** what is worth a full replay and a claim, and nothing it ranks is evidence. Certification
comes from two places only: the sealed fold of a dataset of thousands of markets (7.4's cohort target,
12.8) and the live book (9.5, 11.5). Every claim's `note` carries the sentence.

**Two tiers of fitness** (decision D-R9, ruling R254). A full engine replay per genome is impossible on
hourly and minute grids for a whole population, so a generation scores at two tiers and journals which:

| Tier | What it computes | Who gets it | Where it may reach |
|---|---|---|---|
| `proxy` | the belief function of the genome evaluated on `pmx.features.matrix` (FM1): precomputed integer feature matrices, one row per `(market, bar)` of the fold with the sensor blocks of 18.1 and the market price, giving `prob_ppm` per row; scored by 12.1's time-weighted Brier against the market (`skill_point_micro`, the block-bootstrap `skill_lb_micro`) and `pmv_bp` at one bar; no fills, no fees, no memory, no hive, `descriptors` at their zeros, `pnl_*` zero | every candidate of the generation, on train and on validation | `ranked` and the choice of who gets the engine tier; `candidates_evaluated_cum` |
| `engine` | `run_generation`'s full replay of 12.11 | the elites, the `engine_tier_count` (an `EvolutionConfig` field, default `12`, the elites always included) best by proxy on train, every archive offer (descriptors need fills) and every claim | everything: `elites`, `archive`, `hall_of_fame`, `champion`, `best_validation_lb_micro`, patience, a claim |

`candidate_scored.tier` records the tier with `matrix_hash` and `features_hash` on a proxy row;
`generation_closed.n_engine_tier` and `n_proxy_tier` count them; and **no genome enters a claim on proxy
fitness**: `claim` (12.8) refuses with `ClaimRefusedError` a genome whose store row carries no engine-tier
validation score. The matrix is built once per `(dataset_hash, fold, features_hash)` and cached under
`runs/matrices/` (git-ignored); it reads the training and validation folds through `Dataset.market` and
therefore never a sealed month (ruling R182), and it refuses a showcase dataset (5.6).

**The research budget adjustment** (PRD 5.5, "agents that spend research units and do not convert them
into skill lose the budget in the next generation") is this rule and no other: an agent whose
`skill_lb_micro` did not improve over its own previous generation **and** whose `research_units_spent > 0`
gets `max(0, units - RESEARCH_PENALTY_UNITS)` next generation; every other agent keeps
`config.research_budget_units`. The result is `generation_closed.research_budget_next`, and O2 applies it
by building the next generation's `RunConfig.research_budget_by_agent` from it (sections 8.1 and 9.4).

**The sensor budget is the same rule over the diet** (amendment C1c, 18.1, ruling R235): an agent whose
`skill_lb_micro` did not improve over its own previous generation **and** whose `diet_cost_units > 0`
gets `max(0, allowance - SENSOR_PENALTY_UNITS)` next generation, every other agent keeps
`config.sensor_budget_units`, the result is `generation_closed.sensor_budget_next`, and O2 applies it by
the **sensor drop** of 18.1 on every child whose diet exceeds its allowance (a genome whose required
sensors alone exceed it is culled, `culled_by_budget`). Both budgets are per-bar caps, never cash: fitness
is net of nothing.

**The author's reward** (18.2, ruling R239): for every rule promoted this generation whose author is an
agent of the population, `RULE_AUTHOR_BONUS_MICRO = 5_000` is added to the author's `skill_lb_micro` **for
the ranking of this generation only** (the recorded interval, `candidate_scored` and every claim carry the
unbonused number) and `RULE_AUTHOR_SENSOR_BONUS_UNITS = 2` to its next allowance; for every rule of the
author rejected at the replicate stage or demoted this generation, its next allowance loses
`SENSOR_PENALTY_UNITS`. `generation_closed.rule_rewards` lists every entry. This is how building knowledge
becomes a selected behaviour rather than a hope, and why the bonus never reaches a claim: a claim is about
the sealed fold, not about what the agent taught the others.

**Per-cohort rows** (decision D-S7, ruling R266): the objective is computed over the whole fold, and beside
it every `candidate_scored` and every claim carries one row per cohort of 18.5 with `usable_for_paired_test`
(its own `skill` and `pnl` intervals over the cohort's markets, its own `n`), so that the discovery that an
agent beats the market on `co-kalshi-crypto-bitcoin-threshold-above-month` and nowhere else is on the
record. A cohort row never enters the objective.

The bar (O4, on the **sealed test**, per `(kind, provider)` since amendment C1b (section 17.6, ruling
R162), `n_markets >= CLAIM_MIN_MARKETS = 60`, where on a continuous kind a "market" is an `(instrument,
ISO week)` cell, the skill is the directional skill at the claim's horizon paired against the random walk,
and the permutation shuffles realised returns across instruments within a week):

| Part | Condition | Fields in the claim |
|---|---|---|
| 1 | `skill_lb_micro > 0` (95 percent, block bootstrap, paired against the market) | `skill: Interval` |
| 2 | `n_markets_traded >= CLAIM_MIN_MARKETS` **and** `pnl_lb_cents > 0` (same method on per-market `realised_pnl_cents`) | `pnl: Interval`, `n_markets_traded` |
| 3 | `deflated_lower_bound(skill, candidates=K) > 0 and deflated_lower_bound(pnl, candidates=K) > 0`, with `K` computed by `claims.py` and never passed in (below) | `skill_lb_deflated_micro`, `pnl_lb_deflated_cents`, `candidates`, `candidates_evolution`, `candidates_store`, `candidates_prior_claims` |
| 4 | `permutation_null(...).null_lb_micro <= 0` | `null: NullResult` |

`verdict = "beats_market"` iff all four hold; `"insufficient_n"` when `n_markets < CLAIM_MIN_MARKETS`;
otherwise `"no_demonstrated_edge"`, with every part's boolean beside it; and, on an LLM genome,
`"awaiting_live_replication"` in place of `beats_market` until the live book of 11.5 replicates it
(decision D-R6, ruling R252). Claims on Manifold and on Kalshi
are separate claims and separate `claim_id`s (section 2); nothing is pooled across providers, and since
amendment C1b nothing is pooled across kinds either: a claim names its kind, its provider and its horizon
in its id (section 17.8), and `no_demonstrated_edge` is the expected verdict on a continuous kind and is
reported as such (AC-25). A **per-cohort** row of a claim (18.5, rulings R266 and R283) applies the same four parts
to the cohort's markets with the cohort's own `K` and reads the same three verdicts, plus a fourth that
exists only on a cohort row: a cohort that is not `usable_for_paired_test` carries its counts, no bounds
and `verdict: "not_usable"`, which is a measurement refused and never an edge denied. There is no
per-cohort claim command: one claim, one sealed read, one row per cohort.

**Why part 2 counts traded markets.** The `n_markets >= 60` guard counts forecasts, not trades, so part 2
was clearable by silence: an agent that trades 5 of the 60 sealed markets and abstains from 55 submits a
vector of 5 wins and 55 exact zeros, the zeros carry no variance, and the 95 percent block-bootstrap lower
bound of that mean is comfortably positive (a resample missing all five winning blocks has probability
`(55/60)^60`, about 0.7 percent), while an agent that traded all 60 for the same total PnL fails the same
bound. Rare trading, not skill, cleared the part. With `n_markets_traded >= CLAIM_MIN_MARKETS` inside part
2, an agent that does not trade cannot claim a PnL edge, which is also what the PRD's bar means ("its PnL
after fees is positive with the same bound"); the verdict for such an agent is `no_demonstrated_edge`
with `parts.pnl = false`, and `n_markets_traded` is in the claim and in every leaderboard row so the
reason is visible.

**`K` is computed, never declared.** A human who runs fifty hand-tuned backtests on the validation fold
and claims the best one would otherwise report `K = 8`, and because `claim_id` is keyed on `genome_hash`,
bumping one gene by one produced a fresh unrefused claim with `K` unchanged. Normatively:

```python
K = max(candidates_evolution, candidates_store, candidates_prior_claims + 1, 1)
# candidates_evolution      = candidates_evaluated_cum of the evolution run that produced the genome, else 0
# candidates_store          = distinct genome hashes ever scored against this dataset_hash in pmx.store
# candidates_prior_claims   = claim files plus claims/access.jsonl lines for this dataset_hash
# a per-cohort row (18.5) computes its own K with candidates_prior_claims counted per (dataset_hash, cohort_id)
```

`claims.py` computes all three from the sqlite run index and the claim ledger, records all three and the
chosen `K` in `claims/<claim_id>.json`, and O4's test asserts that a second claim with a one-gene mutation
reports a strictly larger `K`.

### 12.7 Folds and the sealed test (O1, `pmx.optimizer.folds`)

```python
@dataclass(frozen=True, slots=True)
class Folds:
    train_ids: tuple[str, ...]             # fold_key_ms(m) < train_end_ms, canonical order (7.7, ruling R290:
                                           # the cut is on the market's GROUP resolution bar); a continuous
                                           # instrument is in every list whose span intersects its MarketMeta
                                           # life [created_at_ms, resolved_at_ms) (17.6, ruling R186)
    validation_ids: tuple[str, ...]        # train_end_ms <= fold_key_ms(m) < validation_end_ms
    rolling: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...]   # (train 1..k, validate month k+1) for the k in
                                           # 4..9 whose month k+1 ends at or before train_end_ms, ascending in k
                                           # (ruling R277): fewer than six pairs when the training fold is short,
                                           # and FoldIntegrityError from make_folds when it would be empty
    train_end_ms: int; validation_end_ms: int; sealed_count: int   # the count-quantile cuts of 7.7 (ruling R247)
    _sealed_ids: tuple[str, ...]           # private; read by exactly one function below
    cohorts: tuple[Cohort, ...] = ()       # amendment C1c, 18.5 (ruling R266): per-fold counts inside these folds

def make_folds(manifest: DatasetManifest, markets: Sequence[MarketMeta]) -> Folds
def open_sealed_test(folds: Folds, *, claim_id: str, dataset_hash: str, genome_hash: str, provider: str,
                     journal: Journal, ledger_dir: Path, kind: str = "binary") -> tuple[str, ...]
    """The one accessor of the sealed fold. Its one caller is pmx.optimizer.claims.
    It appends a `sealed_test_opened` event (section 9.2) to the journal it is handed AND one line to
    `<ledger_dir>/access.jsonl` before returning any id, so a peek at the sealed fold cannot exist without
    a record of it even when the run is aborted before it writes a claim file. tests/test_architecture.py
    asserts the identifiers `open_sealed_test` and `_sealed_ids` appear nowhere else in src/pmx.
    It returns the sealed ids of `provider` only, in the canonical order of section 3, because a claim is
    per provider (section 12.6) and nothing is pooled across providers. Amendment C1b (17.6, ruling R162):
    it returns the ids of `kind` and `provider` only; for a continuous kind these are the instruments with
    at least one bar inside the sealed months, and the run is clipped to those months."""
```

A continuous instrument does not resolve, so it belongs to **every** fold whose span it has bars in
(amendment C1b, section 17.6): `make_folds` places its bars against the fold spans of 7.7, a run on a
fold carries it when it has a bar inside the fold's span and clips `t0_ms`/`t1_ms` to it, and the
forced flat of 17.3 closes every position at the fold's edge, so no position and no unresolved horizon
crosses from the training span into the validation or the sealed one.

**What `make_folds` reads and refuses** (amendment C1c, rulings R247, R248, R263, R266, R272). The two
headline cuts are the manifest's `split.train_end_ms` and `split.validation_end_ms`, **count quantiles of
group resolution order** (60/20/20 by default, 7.7, ruling R290), and the fold of a market is decided by
`fold_key_ms(m)`, the resolution bar of the latest member of its cluster or `event_key` group, in one step
rather than by a cut followed by a move (`split.cluster_moves` reports the markets whose own bar sits in an
earlier fold); `make_folds` recomputes the cuts, the keys and the realised permille from the metas and
raises `FoldIntegrityError` when they disagree with the manifest, when any group spans two folds or when a
fold is empty, so a dataset built before decision D-R2 is refused rather than silently re-cut.
`Folds.rolling` holds only the pairs whose replicate month ends at or before `train_end_ms` (ruling
R277). It raises
`ShowcaseDatasetError` on a `purpose: "showcase"` dataset before reading a market: a showcase dataset has
no folds. `Folds` gains `cohorts: tuple[Cohort, ...]` (18.5), each with its per-fold counts and
`usable_for_paired_test` (false when any fold is empty, decision D-S13), computed inside the folds and never
across them, so no cohort is measured on a dataset whose folds the fold fix has not reached. The build
target of 7.4 is stated in cohorts, and the manifest's `build.status` says whether this dataset met it.

The earlier text said of this function that "it emits nothing itself", which defeated PRD 2.6 ("the sealed
set is touched by a named claim, logged, and refused on reuse"): a run that opened the sealed fold and
aborted left no trace anywhere, and section 13 puts `claims/` in the git-ignored set, so the file-existence
check of section 12.8 was defeated by deleting a local directory. `claims/` is therefore **tracked**
(`.gitignore` keeps only `claims/*.tmp`), `claims/access.jsonl` is append-only, and each claim carries
`prev_claim_sha256`, the sha256 of the previous claim file of this dataset in `created_at` order (`null`
for the first), so a deletion breaks the chain and is detectable.

Memory and hive states carry forward in time only, through the mechanism of section 9.5 and no other: a
run on the validation fold sets `config.memory_from_run_id` and `config.hive_from_run_id` to the training
run whose `t1_ms <= train_end_ms`, and the runner raises `LeakError` if that run's `t1_ms` is later than
the validation run's `t0_ms`.

### 12.8 Claims (O4, `pmx.optimizer.claims`)

`pmx claim --dataset <name> --genome <path or run_id:agent_id> --provider <provider> [--kind <kind>]
[--horizon-bars <h>]` builds `claim_id = f"c-{dataset_hash[:8]}-{kind}-{provider}-h{horizon_bars}-{genome_hash[:16]}"`
(amendment C1b, sections 17.6 and 17.8, ruling R162; `kind` defaults to `binary`, `horizon_bars` to `0`
on a binary and to the one-day horizon of `default_horizons_bars` otherwise; the v2 spelling
`c-<hash8>-<provider>-<genome16>` is never written again), and **refuses before reading a single sealed
market** if `claims/<claim_id>.json` exists **or** if `claims/access.jsonl` already carries a line for
`(dataset_hash, kind, provider, horizon_bars, genome_hash)` without a completed claim file
(`ClaimRefusedError`, exit code 3): an aborted peek is a used claim, not a free one. It then loads memory and hive as of
`validation_end_ms` (section 12.7) and freezes both, runs the genome on `open_sealed_test(...)` with a
fresh seed derived as `derive_seed(config.seed, f"claim/{claim_id}") % SEED_SPACE`, computes section 12.6,
and writes:

```
claims/<claim_id>.json: claim_id, created_run_id, created_at_index, prev_claim_sha256, dataset_name,
  dataset_hash, contamination_hash | null, genome_hash, genome, provider, kind, horizon_bars, vendor,
  n_units (== n_markets: instruments on a binary, (instrument, week) cells otherwise), n_markets, n_markets_traded,
  n_clean | null, clean_market_ids | null, candidates, candidates_evolution, candidates_store,
  candidates_prior_claims, evolution_run_id | null,
  skill {point, lower, upper, sd, n, n_blocks, resamples}, pnl {...},
  skill_lb_deflated_micro, pnl_lb_deflated_cents, null {null_lb_micro, p_value_ppm, permutations},
  parts {skill: bool, pnl: bool, deflated: bool, null: bool}, verdict, per_tag {tag: {n, skill_point_micro}},
  contract_version, engine_version,
  note (the generator sentence of 12.6 and the continuous expectation of 17.6),
  fitness_tier: "engine" (a claim on a proxy-scored genome is refused, ruling R254),
  capacity {per_market: [{market_id, capacity_cents, halving_scale_permille}], aggregate_cents,
            halving_scale_permille, grid_max_permille}                      (12.3, ruling R255)
  per_cohort: [{cohort_id, lexicon_version, n, n_traded, skill, pnl, skill_lb_deflated_micro,
                pnl_lb_deflated_cents, null, candidates, parts, verdict}]  (18.5, rulings R266, R283, R301:
                one row per cohort of the dataset, each with its own K counted per (dataset_hash, cohort_id);
                a cohort that is not usable_for_paired_test carries its counts, no bounds and
                verdict "not_usable", so a reader sees it was measured and why nothing was concluded)
  rules_used: [{rule_id, live_support, live_lower_bp, n_bars_fired}]     (18.6, ruling R244: the insights the
                                                                            run's rules step or rule_follower read,
                                                                            with their live records AT CLAIM TIME)
  sensors, diet_cost_units, sensor_ablation: [{sensor, run_id, skill_point_micro, skill_drop_micro}] | null
                                                                            (18.1; the table when --ablate-sensors ran)
  labels: [..]  (the dataset's and the roster's labels of 12.10: news_links:weak, taxonomy:weak,
                 contamination_audit:coarse, window_days:<n>)
  live_replication: {n_resolved, skill_lb_micro} | null                  (11.5, ruling R252; LLM genomes)
claims/access.jsonl:    {"claim_id", "dataset_hash", "kind", "provider", "horizon_bars", "genome_hash",
                         "n_markets", "market_ids", "run_id"}      one line, appended before any id is returned
```

`claim` refuses, before any sealed read and in this order: a second claim or an aborted peek
(`ClaimRefusedError`), a `purpose: "showcase"` dataset (`ShowcaseDatasetError`), a dataset whose folds split
a group or has an empty fold (`FoldIntegrityError`), and a genome with no engine-tier validation score
(`ClaimRefusedError`, ruling R254). **There is no `--cohort` flag** (ruling R283): a claim reads the sealed
fold exactly once, per `(dataset_hash, kind, provider, horizon_bars, genome_hash)`, which is the tuple
`claim_id` names and `access.jsonl` is keyed on, and its `per_cohort` rows are the cohort statement. A
per-cohort claim command would have been a second sealed read under a `claim_id` that names no cohort:
either it overwrites the first claim's file or it is refused as an aborted peek, and either way the one
protection PRD 2.6 buys is keyed on a tuple that cannot tell two real claims apart.

The ledger is append-only by convention, by chaining (`prev_claim_sha256`) and by test (a second claim is
refused before any read of the sealed fold; the spy dataset in O1's tests asserts zero reads outside
`claims.py`).

### 12.9 Prompt mutation (O3, `pmx.llm.mutate`)

`worst_markets(projection, agent_id, k=10)` by `skill_micro` ascending; `apropose_patch(gateway,
traces, current: PromptGenome) -> PromptGenome` through the gateway on the configured model (offline tests
use `ScriptedGateway`); `ab_on_validation(parent, child, folds, ...)` runs both on the validation fold
with the same seed; `promote(child) iff child.skill_lb_micro > parent.skill_lb_micro` on validation, never
on train, never on the sealed test. A child that wins on train and loses on validation is rejected, and
that is a test.

**O3 is deferred** (decision D-R11, ruling R256): prompt mutation runs only once the live book of 9.5
holds at least `LIVE_REPLICATION_MIN_RESOLVED = 100` resolved markets, because two and a half months of
clean markets (11.5) are not a set anyone should tune a prompt on. `pmx evolve` refuses `prompt_mutation`
on a roster with LLM seats until then (`NotConfiguredError`, naming the count), the package text above
stands, and the number is a default.

### 12.10 The leaderboard (E5, `pmx.metrics.leaderboard`)

One row per `(agent_id, kind, provider, horizon_bars, fold, category | "all", hardness_tag | "all")`
(`kind` and `horizon_bars` are amendment C1b's, section 17.6, ruling R163; `horizon_bars` is `0` on a
binary row and the pinned baseline of a continuous slice is `random_walk`): `n_markets`,
`n_markets_traded`, `n_markets_open`, `brier_tw_micro`, `skill: Interval`, `pnl: Interval`,
`log_micronats`, `ece_ppm`, `sharpe_milli`, `max_drawdown_bp`, `abstention_ppm`, `explicit_abstain_ppm`,
`fill_ratio_ppm`, `turnover_ppm`, `category_coverage_ppm`, `ruined`, `n_clean` (LLM rows), `verdict`
(claims only), `vendor`, `n_units`, `n_quantile_forecasts`, `pinball_skill: Interval` (the last four
amendment C1b's; `n: 0` on a binary row). The `market_follower` row is present in every slice with `skill.point == 0` by construction
and is pinned by the UI; on a roster of one it is a complete row of zeros, not an exception (section 12's
preamble). Per slice: `n_markets`, `n_markets_traded`, `n_markets_open`, `brier_tw_micro`, `skill`, `pnl`,
`log_micronats`, `n_units`, `n_quantile_forecasts`, `pinball_skill`, and `ece_ppm` where a per-slice ledger
exists; `sharpe_milli`, `max_drawdown_bp`, `fill_ratio_ppm`, `turnover_ppm`, `abstention_ppm`,
`explicit_abstain_ppm`, `category_coverage_ppm` and `ruined` are 12.3's agent-level number repeated on every
slice (ruling R221).

Amendment C1c adds three columns and one slice (rulings R250, R257, R266). `currency` (`mana` iff the row's
provider is `manifold`, decision D-R12): no leaderboard, chart or README sentence pools Manifold with
Kalshi, every Manifold number carries `currency: mana`, and gates G3 onward check it. `labels`, the one
carrier of every quality label a reader must see beside a number (`news_links:weak` from 7.6,
`taxonomy:weak` from 7.14 for the row's venue, `contamination_audit:coarse` on an LLM row from 11.5,
`window_days:<n>` from 5.6 when `n > 365`), filled by `leaderboard.build(..., labels=)` from the manifest
by the caller because the projection reads no dataset. `cohort_id` (`"all"` on today's rows): 12.10 emits
one row per cohort of 18.5 with `usable_for_paired_test`, keyed `(agent_id, kind, provider, horizon_bars,
fold, cohort_id)` with `category` and `hardness_tag` at `"all"`, each with its own `skill` and `pnl`
intervals and its `n_markets`, and the UI shows the cohort's size beside every number of the row.

### 12.11 The structures and signatures that cross a wave

Five packages in three later waves code blind against these, so they are declared here once, field by
field. Every dataclass is `frozen=True, slots=True` and `to_dict()`-able through `canonical_json`.

`Interval` is section 12.4's, `Descriptors` section 12.5's, `CalibrationBinView` section 8.3's (imported
from `pmx.types` by every consumer, ruling R217), and
`JournalEvent` is the union of D7's `pmx.journal.events.*` dataclasses. The remaining names, `SensorInputs`
and `StepTrace` among them (ruling R278), are declared here:

```python
@dataclass(frozen=True, slots=True)
class HorizonBucket:                   # section 12.1
    bucket: str                        # matches RE_HORIZON_BUCKET: one of HORIZON_BUCKETS or an "h<n>" string of 17.5 (R188)
    n_bars: int; brier_tw_micro: int; market_brier_tw_micro: int; skill_micro: int

@dataclass(frozen=True, slots=True)
class LeaderboardRow:                  # section 12.10, one per slice; the listing order IS the dataclass order,
    agent_id: str; provider: str; fold: str; category: str; hardness_tag: str   # and a defaulted field never
    n_markets: int; n_markets_traded: int; n_markets_open: int                    # precedes a required one (R221)
    brier_tw_micro: int; skill: Interval; pnl: Interval; log_micronats: int; ece_ppm: int
    sharpe_milli: int; max_drawdown_bp: int; fill_ratio_ppm: int; turnover_ppm: int
    abstention_ppm: int; explicit_abstain_ppm: int; category_coverage_ppm: int
    ruined: bool; n_clean: int | None; verdict: str | None
    kind: str = "binary"; horizon_bars: int = 0; vendor: str = ""          # amendment C1b, ruling R163
    n_units: int = 0; n_quantile_forecasts: int = 0; pinball_skill: Interval | None = None
    currency: str = "usd"; labels: tuple[str, ...] = (); cohort_id: str = "all"   # amendment C1c, 12.10,
                                                                          # rulings R250, R257, R266

@dataclass(frozen=True, slots=True)
class CandidateScore:                  # section 9.4's candidate_scored payload
    generation: int; agent_id: str; genome_hash: str; fold: str; n_markets: int
    skill_point_micro: int; skill_lb_micro: int; pnl_point_cents: int; pnl_lb_cents: int
    brier_tw_micro: int; ruined: bool; research_units_spent: int; descriptors: Descriptors
    tier: str = "engine"; matrix_hash: str | None = None; features_hash: str | None = None   # 12.6, ruling R254
    diet_cost_units: int = 0; sensors: tuple[str, ...] = (); n_rules_proposed: int = 0         # 18.1, ruling R235
    per_cohort: tuple[CohortScore, ...] = ()                                                  # 18.5, ruling R266

@dataclass(frozen=True, slots=True)
class CohortScore:                     # amendment C1c, 18.5: one cohort's slice of a candidate's score or a claim
    cohort_id: str; n_markets: int; n_markets_traded: int; skill: Interval; pnl: Interval
```

Amendment C1c's two cross-package shapes (ruling R278). `SensorInputs` is what a `sense` body of 18.1 may
read and nothing else, so S1 (which writes fifteen bodies), E1 (which fills it in the `observe` phase)
and FM1 (which fills it per `(market, bar)` for the proxy matrix, with no observation in sight) build
against one declaration. `StepTrace` is exactly the `workflow_step_executed` row of 9.2, which the runner
can get from nowhere but `run_workflow`'s return value:

```python
@dataclass(frozen=True, slots=True)
class SensorInputs:                    # every field as-of at now_ms by the filters of 5.4, never wider
    meta: MarketMeta                   # the leak-free projection of 7.2 (kind, provider, category, tags,
                                       # subject, structure, horizon, cohort_id); None of 7.9's fields
    bars: tuple[Bar, ...]              # the market's COMPLETED bars, oldest first, the run's bars_window
    quotes: tuple[int, int] | None     # (best_bid_bp, best_ask_bp) of the last completed bar, None when unknown
    trades: tuple[Trade, ...]          # the prints of the completed bars, () when the tape carries none
    news: Mapping[str, tuple[NewsView, ...]]   # visible items BY SOURCE, so a news sensor reads its own only
    cash_events: tuple[CashEventView, ...]     # the APPLIED events of 17.3 (ruling R183)
    hive: HiveView | None              # the agent's own hive view of this bar, None under --no-hive
    memory: MemoryView | None          # the agent's own memory view, None when amnesic
    peers: Mapping[str, tuple[Bar, ...]]       # the run's other instruments this market names (twins,
                                       # underlying, cluster peers), their completed bars, for cross_asset
    research: Mapping[str, object]     # the payloads of this agent's GRANTED requests (8.4), by kind
    def to_dict(self) -> dict[str, object]: ...

def run_workflow(workflow: Workflow, *, genome: Genome, obs: Observation,
                 blocks: Mapping[str, Mapping[str, SensorBlock]], memory: MemoryView | None,
                 rng: random.Random) -> tuple[Actions, tuple[StepTrace, ...]]: ...

@dataclass(frozen=True, slots=True)
class StepTrace:                       # one per executed step, in topological order; the 9.2 payload
    step_index: int; kind: str; ref: str | None
    n_inputs: int; n_out: int; output_sha256: str
```

```python
# ---- the projection (E5, pmx.metrics.projection) --------------------------------------------------
@dataclass(frozen=True, slots=True)
class PerMarket:                       # one row per (agent, market); the input of every Interval
    agent_id: str; market_id: str; provider: str; category: str; tags: tuple[str, ...]
    block_key: str; fold: str; hardness_tags: tuple[str, ...]
    n_forecast_bars: int; agent_brier_tw_micro: int; market_brier_tw_micro: int; skill_micro: int
    log_micronats: int; pmv_1d_bp: int; pmv_7d_bp: int
    realised_pnl_cents: int; fees_cents: int; n_fills: int; abstained_bars: int; traded: bool
    kind: str = "binary"; horizon_bars: int = 0; unit_key: str = ""       # amendment C1b, 17.6: one row per
    dir_brier_micro: int = 0; pinball_micro: int = 0; baseline_pinball_micro: int = 0   # (agent, instrument, week,
    n_resolved: int = 0; n_cash_events: int = 0                             # horizon) on a continuous kind
    n_quantile_forecasts: int = 0          # the cell's resolved forecasts whose quantiles_ticks was not null (ruling
                                           # R221, declared here and filled by E5 in the next lot; the row's column is its sum)
    cohort_id: str | None = None           # amendment C1c, 18.5 (rulings R266 and R288): read off
                                           # market_listed.cohort_id once R274's lot journals it; None until
                                           # then and on a market that belongs to no cohort

@dataclass(frozen=True, slots=True)
class AgentResult:
    agent_id: str; family: str; kind: str; genome_hash: str; ruined: bool
    n_markets: int; n_markets_traded: int; n_markets_open: int
    brier_tw_micro: int; skill: Interval; pnl: Interval
    pnl_cents: int; return_bp: int; max_drawdown_bp: int; sharpe_milli: int
    turnover_cents: int; fill_ratio_ppm: int; fees_paid_cents: int
    abstention_ppm: int; explicit_abstain_ppm: int
    descriptors: Descriptors                                     # section 12.5, the five of them
    calibration: tuple[CalibrationBinView, ...]; horizons: tuple[HorizonBucket, ...]
    research_units_spent: int
    pinball_skill: Interval | None = None                        # amendment C1b, 17.6
    exposure_by_kind: tuple[tuple[str, int], ...] = ()           # (kind, mean absolute marked notional in cents)
    n_cash_events: int = 0
    ece_ppm: int = 0; sharpness_ppm: int = 0                      # 12.2 over the agent's own slice (ruling R221)

@dataclass(frozen=True, slots=True)
class MarketResult:
    market_id: str; provider: str; category: str; fold: str; block_key: str
    outcome: int; n_bars: int; market_brier_tw_micro: int; life_mean_price_bp: int
    hardness_tags: tuple[str, ...]
    kind: str = "binary"; vendor: str = ""; last_price_ticks: int = 0   # amendment C1b: outcome is -1 and
                                                                         # life_mean_price_bp the mean close in
                                                                         # ticks on a continuous instrument

@dataclass(frozen=True, slots=True)
class RunProjection:
    run_id: str; dataset_hash: str; config_hash: str; interval_min: int; t0_ms: int; t1_ms: int
    liquidity: str; liquidity_params_hash: str                   # section 16.1, read from run_started.config
    seed: int                                                    # read from run_started.config too (ruling R221, declared
                                                                 # here and filled by E5 in the next lot); leaderboard.build
                                                                 # builds its RngTree from it and never from the run id
    agents: tuple[AgentResult, ...]                              # sorted by agent_id
    markets: tuple[MarketResult, ...]                            # canonical market order
    per_market: tuple[PerMarket, ...]                            # sorted by (agent_id, market_id, horizon_bars, unit_key) (R199)
    ruined_agent_ids: tuple[str, ...]
    def to_dict(self) -> dict[str, object]: ...

def project(events: Sequence[JournalEvent]) -> RunProjection: ...
# results.json is canonical_json(projection.to_dict()) + "\n" and nothing else (section 9.5)

@dataclass(frozen=True, slots=True)
class RunHandle:
    run_id: str; run_dir: Path; journal_path: Path; journal_hash: str
    dataset_hash: str; config_hash: str
    projection: RunProjection
    n_events: int; n_bars: int; ruined_agent_ids: tuple[str, ...]

# ---- the runner (E5, pmx.engine.runner) ----------------------------------------------------------
def run_backtest(dataset: Dataset, roster: Sequence[Agent], config: RunConfig, *,
                 tree: RngTree, journal_dir: Path, liquidity: LiquidityModel,
                 gateway: Gateway | None = None,
                 memory: Mapping[str, Memory] | None = None, hive: Hive | None = None,
                 dump_observations: bool = False) -> RunHandle: ...
def replay(run_dir: Path) -> RunProjection: ...      # journal only; asserts byte equality with results.json
```

`tree` is required and keyword-only (section 6.2: the runner never builds one), `memory` is one `Memory`
per `agent_id` and `hive` one hive for the run; when either is `None` the runner runs without it and emits
no `memory_written` / `hive_written`, which is exactly what wave 2's scripted-stub gate run produces.
`liquidity` is amendment C1's addition (section 16.1) and it is **required and keyword-only, exactly like
`tree`** (ruling R139): the runner never builds a model, it receives one and hands it to `Execution`.
Every caller builds its own with `pmx.engine.liquidity.make_liquidity(config)`, which is what E5's
`pmx.cli_run`, O2's `run_generation` and O4's `claim` do. The earlier spelling, a defaulted
`LiquidityModel | None` whose `None` meant "build the one `config.liquidity` names", said in one sentence
both that the runner never builds a model and that it builds one; a default that contradicts its own
paragraph is a defect, not a convenience. The runner raises `InvalidConfigError` when the model it was
handed reports a `model_id` or a `params_hash` that does not match `config.liquidity` and
`config.liquidity_params_hash`, so a journal can never claim a liquidity it did not run under.

```python
# ---- the optimizer (O1 pmx.optimizer.tournament, O2 pmx.optimizer.evolution and archive) ---------
@dataclass(frozen=True, slots=True)
class EvolutionConfig:
    seed: int
    population_size: int = 48
    max_generations: int = 30
    cull_permille: int = 400
    elite_count: int = 4
    immigrant_count: int = 4
    crossover_permille: int = 300
    structural_permille: int = 100
    reset_permille: int = 50                 # the gene-reset probability of section 10.1
    novelty_weight_permille: int = 200
    patience: int = 6
    validate_every: int = 1
    research_budget_units: int = 10
    run: RunConfig | None = None             # the template every generation's backtest starts from
    # Amendment C1c (18.1, 12.6; rulings R235, R254): every value below is a default the first evolution reports
    # against, and every one enters to_dict() and therefore config_hash.
    sensor_budget_units: int = 17            # SENSOR_BUDGET_UNITS_DEFAULT: a fresh genome's per-bar diet allowance
    sensor_mutation_permille: int = 100      # the probability a mutation adds or removes one sensor
    engine_tier_count: int = 12              # candidates replayed at the engine tier per generation, elites included
    ablate_sensors: bool = False             # re-run the champion once per sensor of its diet at the end (18.1)
    def to_dict(self) -> dict[str, object]: ...
    @property
    def config_hash(self) -> str: ...        # sha256(canonical_json(self.to_dict()))

@dataclass(frozen=True, slots=True)
class GenerationResult:
    generation: int
    train: tuple[RunHandle, ...]; validation: tuple[RunHandle, ...]
    scored: tuple[CandidateScore, ...]       # one per (agent, fold), the candidate_scored payloads
    ranked: tuple[str, ...]                  # agent ids, objective descending (section 12.6)

def run_generation(*, generation: int, population: Sequence[tuple[str, Genome]], folds: Folds,
                   dataset: Dataset, config: EvolutionConfig, tree: RngTree,
                   journal: Journal, journal_dir: Path) -> GenerationResult: ...

def evolve(dataset: Dataset, *, config: EvolutionConfig, journal_dir: Path,
           gateway: Gateway | None = None) -> RunHandle: ...
def resume(run_id: str, *, journal_dir: Path, generation: int | None = None,
           gateway: Gateway | None = None) -> RunHandle: ...

class Archive:                               # pmx.optimizer.archive, the MAP-Elites grid of section 12.5
    def __init__(self, *, cells: int = ARCHIVE_CELLS) -> None: ...
    def cell_key(self, descriptors: Descriptors) -> str: ...
    def offer(self, *, cell_key: str, agent_id: str, genome: Genome, skill_lb_micro: int) -> bool: ...
    def occupants(self) -> tuple[tuple[str, str, str, int], ...]:  # (cell_key, agent_id, genome_hash, lb)
    def filled(self) -> int: ...
    def to_dict(self) -> dict[str, object]: ...
```

### 12.12 The HTTP surface (U1 declares it, U2 and U3 consume it)

U2 and U3 run in the same wave as U1 and must call it blind, so the routes are contract. Read routes are
open on localhost; every write route requires the header `X-Pmx-Token: <token>` matching
`PMX_API_TOKEN` and answers `401` without it. Every response that carries a score also carries `run_id`
and `dataset_hash` (PRD 7.2). All bodies are JSON in the units of section 1.

| Method and path | Answers |
|---|---|
| `GET /health` | `{"ok": true, "pmx_version", "contract_version", "engine_version"}` |
| `GET /datasets` | `[{name, freeze_date, interval_min, providers, counts, sealed, dataset_hash, purpose, window_days}]`, research datasets first, newest first (decision D-S2, ruling R261: the UI's default dataset is the newest sealed research dataset and **never** a showcase one, which is reachable only through an explicit selector that labels it `showcase`) |
| `GET /datasets/{name}` | the manifest of section 7.8, verbatim |
| `GET /datasets/{name}/verify` | `{"ok": bool, "dataset_hash", "expected", "mismatched_files": [..]}` |
| `GET /datasets/{name}/markets` | `[MarketMeta]` (section 7.2), server-side paged by `?limit=&cursor=`, filtered by `?category=&subject=&structure=&horizon=&provider=&fold=&hardness_tag=&outcome=&cohort_id=` and sorted by `?sort=resolved_at_ms|life_days|volume_milli_total|final_price_bp` (decision D-S10, ruling R269; `outcome` and `final_price_bp` are the resolved market's, which a dataset browser may show, 14's U2 rule) |
| `GET /datasets/{name}/cohorts` | `[Cohort.to_dict()]` of 18.5 with per-fold counts and the two flags; `?usable=true` narrows |
| `GET /datasets/{name}/cohorts/{cohort_id}` | the cohort's markets side by side and, `?run_id=`, each agent's calibration table on that cohort (the cohort view of decision D-S10) |
| `GET /rules` | the rule ledger of 18.2: `[{rule, family_id, status: "proposed"\|"rejected"\|"promoted"\|"demoted", test, live, transfer}]`, filtered by `?dataset_hash=&status=&author_id=&cohort_id=` |
| `GET /rules/{rule_id}` | one rule with every `rule_tested` row and, `?run_id=`, the bars it fired on |
| `GET /markets/{market_id}` | one market: metadata, `bars`, `trades`, linked news; `?as_of_ms=` applies the as-of filter of section 5.4 and hides the outcome until `as_of_ms >= resolved_at_ms` |
| `GET /runs` | `[{run_id, kind, dataset_name, dataset_hash, fold, seed, config_hash, n_bars, created_at_index}]` |
| `GET /runs/{run_id}` | the run manifest of section 9.5 |
| `GET /runs/{run_id}/journal` | the journal, paged by `?from_seq=&limit=`, one event per array item |
| `GET /runs/{run_id}/results` | `results.json`, verbatim (`RunProjection.to_dict()`) |
| `GET /runs/{run_id}/leaderboard` | `[LeaderboardRow]` (section 12.10), filtered by `?provider=&fold=&category=&hardness_tag=&kind=&horizon_bars=&cohort_id=` (`kind` and `horizon_bars` since amendment C1b, `cohort_id` since C1c); every row carries `currency` and `labels` (ruling R257) |
| `GET /claims/{claim_id}/ablation` | the claim's `sensor_ablation` table of 18.1, or `404` when the claim ran without `--ablate-sensors` |
| `GET /runs/{run_id}/calibration` | `[{agent_id, bins, ece_ppm, sharpness_ppm, horizons}]` |
| `GET /evolutions` | `[{run_id, dataset_hash, generations_run, champion}]` |
| `GET /evolutions/{run_id}/generations` | `[generation_closed payloads]` (section 9.4) |
| `GET /hive` | `?run_id=&now_ms=&kind=&market_id=` , `[HiveEntry]` with the as-of filter applied |
| `GET /claims` | the ledger: `[claims/<claim_id>.json]`, newest first |
| `GET /claims/{claim_id}` | one claim, verbatim |
| `GET /live/book` | `{pending: [...], resolved: [...], score: {...}}` from `live/` (section 9.5) |
| `POST /runs` | body `{kind: "backtest"\|"evolution", dataset, config, roster\|population, seed}`, answers `202 {"job_id"}` |
| `POST /claims` | body `{dataset, genome, provider, kind?, horizon_bars?, ablate_sensors?}`, answers `202 {"job_id"}` (no `cohort_id`: a claim reads the sealed fold once and reports its `per_cohort` rows, ruling R283) |
| `GET /jobs/{job_id}` | `{job_id, kind, state: "queued"\|"running"\|"done"\|"failed", run_id\|null, error\|null, progress_permille}` |
| `GET /jobs/{job_id}/events` | server-sent events, `event:` one of `job_queued`, `job_started`, `bar_progress`, `generation_closed`, `job_done`, `job_failed`, `data:` a JSON object carrying `job_id` and the payload |

---

## 13. Module map and file ownership

Every file has exactly one owning package. A package creates or edits only the files listed against it,
plus fixtures under `tests/fixtures/<package>/`. `__init__.py` files carry a docstring and nothing else
(the top level `src/pmx/__init__.py` also carries the version constants); submodules import by full path.
The gate that closes a wave may edit any file to resolve reported contract issues, and records what it
changed in section 15. Scratch files live in the agent scratchpad and never in the repository (`.scratch/`
is git-ignored, ruling R218). A `pmx.types` constant is imported from `pmx.types`; a module that re-exports
another module's name does so explicitly (`from pmx.types import X as X`) and no module is required to declare
`__all__` (ruling R224). The engine's structural protocols have one declaration each: `InstrumentLike`,
`CashEventLike`, `BarLookups`, `CashEventStamp` and `InstrumentClock` in `engine/calendar.py`, the read side
`MemoryLike` and `HiveLike` in `engine/observation.py`, extended by the runner's write-side protocols (ruling
R205).

```
prediction_market/
  pyproject.toml                                  U4   (C0 wrote the v2 baseline)
  run.bat                                         U4
  README.md                                       U4
  .gitignore                                      C0
  docs/PRD_V2_HARD_OPTIMIZER.md                   input, never edited by a package
  docs/PLAN_V2_WAVES.md                           input; amended only by a part-2 amendment package
                                                  (C1..C5), which records the change in section 15
  docs/CONTRACTS_V2.md                            C0, then the amendment package of each part-2 wave
                                                  (C1..C5, and C1b for section 17); gates append to section 15
  docs/BUILD_STATE.md                             U4 (gates G1..G6 write their paragraphs through U4's file)
  configs/models.json                             A5   (model ids and knowledge cutoffs)
  data/demo_v1/                                   D1   (generated by migrate-v1, committed)
  src/pmx/py.typed                                U4   (ruling R99, packaged with the data files)
  src/pmx/lexicons/stopwords.v1.json              D5   (ruling R94 moved these inside the package)
  src/pmx/lexicons/paraphrases.v1.json            D5   ({"paraphrases": [str, str, str]}, used by A6)
  src/pmx/lexicons/<category>.v1.json             D5   (12 files, one per category of section 2)
  src/pmx/lexicons/kalshi_series_subjects.v1.json D2   (ruling R169: the sealed series-to-subjects map)
  src/pmx/lexicons/kalshi_series_categories.v1.json D2 (ruling R170: the sealed series-ticker-to-category map)
  src/pmx/lexicons/fin_<topic>.v1.json            F3   (the four finance lexicons of section 17.7)
  src/pmx/lexicons/tags.v1.json                   DS2  (the three-facet vocabulary of 7.14, ruling R265)
  src/pmx/lexicons/kalshi_series_facets.v1.json   DS2  (the series-to-facets map of 7.14; never supersedes
                                                  D2's kalshi_series_subjects.v1.json, ruling R295)
  data/datasets/                                  generated, git-ignored (contamination.json included)
  audits/<dataset_hash[:16]>/                     DS1, DS2 write, gate G3 reviews; TRACKED evidence like
                                                  claims/ (the two human audits of 7.6 and 7.14, ruling R296)
  runs/  live/                                    generated, git-ignored
  analysis/<dataset>/                             generated, git-ignored: detector outputs (section 16.4)
  models/                                         generated, git-ignored: exported policies and cards
                                                  (section 16.5); their hashes are tracked in claims/
  claims/                                         generated but TRACKED (section 12.7): the ledger is
                                                  evidence, so only claims/*.tmp is ignored
  src/pmx/
    __init__.py                                   C0   (docstring, __version__, ENGINE_VERSION, CONTRACT_VERSION)
    v1/**                                         frozen legacy; no package edits it
    schemas/market.v2.json                        C0   (section 7.13: inside the package, not at the root)
    schemas/news.v1.json                          C0
    schemas/dataset.v1.json                       C0
    schemas/actions.v2.json                       C0   (handed to the CLI through --json-schema by A5)
    schemas/journal.v2.json                       C0
    schemas/cluster.v1.json                       C1   (amendment C1, section 16.3)
    schemas/opportunity.v1.json                   C1   (section 16.4)
    schemas/features.v1.json                      C1   (section 16.5)
    schemas/model_card.v1.json                    C1   (section 16.5)
    schemas/instrument.v1.json                    C1b  (amendment C1b, section 17.1)
    schemas/cash_event.v1.json                    C1b  (section 17.3)
    schemas/session_calendar.v1.json              C1b  (section 17.2)
    schemas/forecast.v1.json                      C1b  (section 17.5)
    schemas/rule.v1.json                          C1c  (amendment C1c, section 18.2)
    schemas/sensor.v1.json                        C1c  (section 18.1)
    schemas/workflow.v1.json                      C1c  (section 18.4)
    types.py                                      D1
    errors.py                                     D1   (the error taxonomy of section 13.1)
    rng.py                                        D7
    journal.py                                    D7
    scoring.py                                    E3
    store.py                                      E5   (sqlite run index)
    cli.py                                        U4   (the argparse tree only: it builds the parser and
                                                       dispatches to each cli_*.register(subparsers))
    cli_run.py                                    E5   (pmx backtest with --roster-module, pmx replay; R200)
    cli_rules.py                                  S2   (pmx rules mine|test|ledger, section 18.2)
    cohorts.py                                    DS2  (Cohort, list_cohorts, RE_COHORT_ID, section 18.5)
    cli_evolve.py                                 O2   (pmx evolve, pmx resume)
    cli_claim.py                                  O4   (pmx claim)
    cli_data.py                                   D6
    cli_audit.py                                  A6   (pmx audit contamination; pmx audit leaks runs the
                                                       four families named in ruling R225)
    cli_live.py                                   L1
    cli_analyze.py                                R2e  (pmx analyze <detector>, pmx analyze all)
    cli_learn.py                                  R3d  (pmx learn train, pmx learn export)
    cli_adversary.py                              R4b  (pmx adversary coevolve)
    cli_portfolio.py                              R5a  (ruling R123: PRD v3 section 10 names it and
                                                       PLAN_V3_WAVES omits it, so R5a owns it)
    data/__init__.py                              C0
    data/schema.py                                D1
    data/loader.py                                D1
    data/migrate_v1.py                            D1
    data/resample.py                              D6
    data/builder.py                               DS1  (D6 wrote it; DS1 owns it from lot 5b for the fold fix, the
                                                       window, the purpose, the universe rule and the hourly build
                                                       of section 18 (ruling R245); DS2 adds the tagging and
                                                       cohort-listing calls of 7.14 and 18.5 by the agreement this
                                                       map records, and R1d the hourly option by ruling R123's)
    data/loader.py                                DS1  (D1 wrote it; DS1 owns it from lot 5b: purpose, window_days,
                                                       the count-quantile cuts and cluster moves, the per-source
                                                       lag, the taxonomy/ walk; DS2 adds the facet and cohort
                                                       reads by the agreement this map records)
    data/taxonomy.py                              DS2  (the deterministic tagger of 7.14)
    data/showcase.py                              DS2  (the showcase pack of decision D-S5)
    data/universe.py                              DS1  (the documented universe rule of 7.4; R1a keeps the
                                                       statistics of PRD v3 3.1 and adds them here by agreement)
    data/clusters.py                              R1b  (EventCluster, Constraint, residuals, section 16.3)
    data/impact.py                                R1c  (the impact calibration projection, section 16.1)
    data/embeddings.py                            R3b  (as-of text embeddings at build time, section 16.5)
    data/sessions.py                              D1   (in_session, next_bar_ms, load_calendar, the synthesised
                                                       continuous calendar and the generator; section 17.2, ruling
                                                       R174: gate G2 applies it because E1, E2 and the loader
                                                       call it in wave 2; SessionCalendar itself is in types.py)
    data/calendars/*.json                         F4   (the static session calendars generated through
                                                       pmx.data.sessions; releases.v1.json is F3's)
    data/calendars/releases.v1.json               F3   (the FOMC, CPI and payrolls release calendar)
    data/universe_finance.py                      F4   (the dated finance universe of PRD v4 2.2)
    data/importers/__init__.py                    C0
    data/importers/_http.py                       D2   (the one HTTP client: throttle, cache, User-Agent, backoff)
    data/importers/kalshi.py                      D2
    data/importers/manifold.py                    D3
    data/importers/polymarket.py                  D4
    data/importers/metaculus.py                   D2   (optional, token-gated; stub that raises NotConfigured until built)
    data/importers/binance.py                     F1   (klines, aggTrades, funding; spot_crypto and perp; the
                                                       1-minute path and liquidation instants of section 18.3)
    data/importers/kraken.py                      F1
    data/importers/coinbase.py                    F1
    data/importers/bybit.py                       F1   (linear klines; perp)
    data/importers/yahoo.py                       F2   (equities, ETFs, continuous futures, FX; vendor yahoo)
    data/importers/frankfurter.py                 F2   (daily FX reference rates)
    data/importers/ecb.py                         F2   (daily FX reference rates, the official anchor)
    data/news/__init__.py                         C0
    data/news/wikipedia_current_events.py         DS1  (D5 wrote it; DS1 owns it for the per-bullet revision
                                                       timestamps of decision D-R3, section 5.5)
    data/news/wikipedia_asof.py                   D5
    data/news/wayback.py                          D5
    data/news/gdelt.py                            D5
    data/news/linker.py                           DS1  (D5 wrote it; DS1 owns it for the audit tooling of 7.6)
    data/news/hn.py                               F5   (Hacker News through Algolia, section 18.3)
    data/news/timestamped.py                      F5   (the admission rule and the per-source lag of 18.3)
    data/news/manifold_comments.py                D3
    data/news/edgar.py                            F3   (SEC submissions as filings, as-of by acceptance time)
    data/news/fred.py                             F3   (ALFRED vintages; a series without one is features-only)
    data/news/release_calendar.py                 F3
    data/news/cboe.py                             F3   (VIX history)
    engine/__init__.py                            C0
    engine/calendar.py                            E1
    engine/observation.py                         E1
    engine/execution.py                           E2
    engine/fees.py                                E2
    engine/liquidity.py                           E2   (the LiquidityModel protocol, the envelope check
                                                       and `historical`, section 16.1; R1c adds
                                                       `calibrated_impact` in wave 7 by the agreement of
                                                       ruling R123, and the file stays E2's)
    engine/runner.py                              E5
    agents/__init__.py                            C0
    agents/protocol.py                            A1
    agents/registry.py                            A1
    agents/workflow.py                            A1   (Workflow, Step, linear_workflow, run_workflow; section 18.4)
    agents/memory.py                              A2
    agents/hive.py                                A3
    agents/ensembles.py                           A4
    agents/families/__init__.py                   C0
    agents/families/follower.py                   A1
    agents/families/trend.py                      A1
    agents/families/revert.py                     A1
    agents/families/timedecay.py                  A1
    agents/families/volume.py                     A1
    agents/families/breakout.py                   A1
    agents/families/newsbayes.py                  A1
    agents/families/calibrator.py                 A1
    agents/families/specialist.py                 A1
    agents/families/kelly.py                      A1
    agents/families/legacy.py                     A1   (the v1 archetypes not expressible as genes)
    agents/families/stacker.py                    A4
    agents/families/torch_policy.py               R3e  (the exported-policy family, section 16.5)
    agents/families/random_walk.py                A1   (the continuous baseline of section 17.5, zero skill)
    agents/families/carry.py                      A1   (section 17.7)
    agents/families/basis.py                      A1
    agents/families/pairs.py                      A1
    agents/families/vol_regime.py                 A1
    agents/families/calendar.py                   A1
    agents/families/rule_follower.py              A1   (section 18.2, ruling R240)
    sensors/__init__.py                           C1c  (ruling R122: created by this amendment, docstring only)
    sensors/catalogue.py                          S1   (SENSORS, SENSOR_NAMES, CATALOGUE_HASH, SENSOR_BY_NEWS_SOURCE,
                                                       SensorSpec, SensorBlock, RE_SENSOR; section 18.1)
    sensors/<sensor>.py                           S1   (one module per sensor of the catalogue; the sense function)
    rules/__init__.py                             C1c  (ruling R122)
    rules/vocabulary.py                           S2   (FEATURE_NAMES over the sensor blocks)
    rules/rule.py                                 S2   (Predicate, RuleScope, RuleClaim, Rule, rule_from_dict, RE_RULE_ID)
    rules/tester.py                               S2   (HypothesisFamily, FamilyTemplate, the tester of 18.2, RE_FAMILY_ID;
                                                       adds benjamini_hochberg to metrics/stats.py by agreement, R238)
    rules/miner.py                                S2   (the symbolic miner of 18.2)
    gateway/__init__.py                           C0
    gateway/protocol.py                           A5
    gateway/budget.py                             A5
    gateway/claude_cli.py                         A5
    gateway/prompt.py                             A5
    gateway/scripted.py                           A5
    llm/__init__.py                               C0
    llm/forecaster.py                             A5
    llm/prompts/frame.v1.md                       A5
    llm/prompts/<dial>.<level>.md                 A5   (7 dials x 5 levels)
    llm/contamination.py                          A6
    llm/mutate.py                                 O3
    metrics/__init__.py                           C0
    metrics/projection.py                         E5
    metrics/calibration.py                        E3
    metrics/performance.py                        E5
    metrics/behavioral.py                         E5
    metrics/stats.py                              E4   (S2 adds benjamini_hochberg by the agreement of ruling R238)
    metrics/capacity.py                           O4   (the capacity metric of 12.3, computed at claim time)
    metrics/leaderboard.py                        E5
    optimizer/__init__.py                         C0
    optimizer/folds.py                            O1
    optimizer/tournament.py                       O1
    optimizer/evolution.py                        O2
    optimizer/archive.py                          O2
    optimizer/claims.py                           O4
    live/__init__.py                              C0
    live/fetch_open.py                            L1
    live/forecast_job.py                          L1
    live/resolve_job.py                           L1
    live/book.py                                  L1
    api/__init__.py                               C0
    api/app.py                                    U1
    api/routes_read.py                            U1
    api/routes_jobs.py                            U1
    api/sse.py                                    U1
    api/worker.py                                 U1
    api/routes_analysis.py                        R2e  (the analysis routes, section 16.4)
    api/routes_rules.py                           U1   (the rule ledger, cohort and ablation routes of 12.12)
    analysis/__init__.py                          C2   (ruling R122)
    analysis/news_lead.py                         R2a
    analysis/divergence.py                        R2b
    analysis/logic.py                             R2c
    analysis/comparative.py                       R2d
    analysis/report.py                            R2e  (the opportunity map and RE_OPPORTUNITY_ID)
    analysis/cross_domain.py                      R2f  (the cross-domain detectors of section 17.6)
    features/__init__.py                          C1c  (ruling R122 as ruling R245 applies it: FM1 opens features/
                                                       in lot 6, before amendment C3, so this amendment creates the
                                                       docstring-only file)
    features/matrix.py                            FM1  (the precomputed integer feature matrices of the proxy tier,
                                                       section 12.6, decision D-R9)
    features/spec.py                              R3a  (the layout of section 16.5 and features_hash)
    features/build.py                             R3a
    features/view.py                              R3a  (the float view, the one crossing into torch)
    features/quantise.py                          R3a  (ppm and integer positions, ruling R120)
    learn/__init__.py                             C3   (ruling R122)
    learn/supervised.py                           R3c
    learn/env.py  learn/ppo.py  learn/es.py       R3d
    learn/policies.py  learn/export.py  learn/cards.py   R3d
    learn/llm_finetune.py                         R5c  (optional, GPU; an offline stub in the test)
    adversary/__init__.py                         C4   (ruling R122)
    adversary/mm.py                               R4a  (the adversarial_mm LiquidityModel, section 16.1)
    adversary/coevolution.py                      R4b
    adversary/stress.py                           R4c
    adversary/train/__init__.py                   C4   (ruling R122)
    adversary/train/policy.py  adversary/train/loop.py   R4d
    portfolio/__init__.py                         C5   (ruling R122)
    portfolio/allocator.py  portfolio/governor.py R5a
    portfolio/meta.py                             R5b
    live/opportunities.py                         R6a
  tests/
    conftest.py                                   C0   (v1 fixtures kept; v2 fixtures added by the gate)
    test_engine.py  test_data_and_metrics.py  test_api.py     frozen v1 tests (import pmx.v1)
    test_architecture.py                          C0 / gates, extended by C1..C5 and C1b
    test_contract_schemas.py                      C0, extended by C1..C5 and C1b
    test_types_loader.py                          D1
    test_import_kalshi.py                         D2
    test_import_manifold.py                       D3
    test_import_polymarket.py                     D4
    test_news.py                                  D5
    test_builder.py                               D6
    test_rng_journal.py                           D7
    test_observation.py                           E1
    test_execution.py                             E2
    test_scoring.py                               E3
    test_stats.py                                 E4
    test_runner.py                                E5
    stub_roster.py                                E5   (the scripted-stub roster of gate G2, ruling R200;
                                                       not a test file, never imported by src/)
    stub_roster_rng.py                            E5   (that roster plus the seed-consuming coin_flipper,
                                                       ruling R229; same rules as the line above)
    test_agents_families.py                       A1
    test_memory.py                                A2
    test_hive.py                                  A3
    test_stacker.py                               A4
    test_gateway.py  test_llm_forecaster.py       A5
    test_contamination.py                         A6
    test_folds.py                                 O1
    test_evolution.py                             O2
    test_mutate.py                                O3
    test_claims.py                                O4
    test_api_v2.py                                U1
    test_live.py                                  L1
    test_universe.py                              R1a
    test_clusters.py                              R1b
    test_liquidity.py                             R1c  (E2's own protocol tests are in test_execution.py)
    test_hourly.py                                R1d
    test_news_lead.py                             R2a
    test_divergence.py                            R2b
    test_logic.py                                 R2c
    test_comparative.py                           R2d
    test_analyze_cli.py                           R2e
    test_features.py                              R3a
    test_embeddings.py                            R3b
    test_supervised.py                            R3c
    test_learn.py                                 R3d
    test_torch_policy.py                          R3e
    test_adversary_mm.py                          R4a
    test_coevolution.py                           R4b
    test_stress.py                                R4c
    test_adversary_train.py                       R4d
    test_portfolio.py                             R5a
    test_meta.py                                  R5b
    test_import_crypto.py                         F1
    test_import_yahoo_fx.py                       F2
    test_finance_news.py                          F3
    test_sessions_universe.py                     F4
    test_sensors.py                               S1   (fixtures/s1/)
    test_rules.py                                 S2   (fixtures/s2/: the planted effect and its shuffled twin, AC-27)
    test_hn.py                                    F5   (fixtures/f5/)
    test_taxonomy.py  test_cohorts.py  test_showcase.py   DS2 (fixtures/ds2/)
    test_feature_matrix.py                        FM1
    test_workflow.py                              A1
    e2e/test_e2e_5a_discovery.py                  gate G4 (PRD v5's E2E-5a as ruling R238 corrects it)
    e2e/test_e2e_0_base.py                        gate G6 (ruling R137): the first point at which build,
                                                  run, replay and claim all exist, which is what rung 0
                                                  of PRD v3 section 2 asks an end-to-end test to cover
    e2e/test_e2e_<n>_<name>.py                    the gate of the rung (G7..G11); no package writes here
    e2e/test_e2e_1b_multi_asset.py                G3b  (gate G3b, PRD v4 section 7: the mixed-roster fixture run)
    e2e/test_e2e_2b_cross_domain.py               G8   (gate G8, PRD v4 section 7: the planted mispricing and its null)
    fixtures/<package>/**                         the package
    fixtures/contract/**                          C0, extended by C1..C5 and C1b
  web/
    src/api.ts  src/types.ts                      U1   (the typed mirror of section 12.12; U1 owns both
                                                       sides of the HTTP boundary, U2 and U3 import them)
    src/util.ts                                   U2
    src/components/market/**  src/components/portfolio/**       U2
    src/components/clusters/**                    R1d
    src/components/opportunities/**               R2e
    src/components/rules/**  src/components/cohorts/**   U3  (the rule ledger, the ablation table, the cohort view)
    src/components/portfolio_alloc/**  src/components/live_opportunities/**   R6b
    src/components/board/**  src/components/evolution/**  src/components/hive/**
    src/components/claims/**  src/components/dataset/**  src/components/live/**   U3
    src/App.tsx  src/styles.css                   U3
    index.html  src/main.tsx  package.json  tsconfig.json  vite.config.ts        U3
    src/components/{Leaderboard,MarketReplay,PriceChart,WalkForwardView}.tsx     U3 (v1; U3 deletes
                                                       them in the same commit that lands board/)
```

`web/src/api.ts` and `web/src/types.ts` moved from U2 to U1 in wave 0 because U3 needs a dozen fetchers
and a dozen types in them, which would have been a guaranteed cross-owner edit; they are generated from
the one route list of section 12.12, which U1 also implements, so the two sides cannot drift.

Two files of the PRD's map are renamed here and the PRD reading is superseded: `data/news/linker.py`
is an engine-side pure module (it reads no socket; it scores stored items), and every news fetcher uses
`data/importers/_http.py` rather than `httpx` directly, which is what lets the socket rule of
`tests/test_architecture.py` stay literal. `errors.py`, `store.py`, `cli_data.py`, `cli_run.py`, `cli_evolve.py`, `cli_claim.py`, `cli_audit.py`,
`cli_live.py`, `agents/ensembles.py`, `agents/families/legacy.py`, `optimizer/archive.py`,
`configs/models.json` and `llm/prompts/` are additions the plan names or implies; their owners are above.
The plan gives E5 `pmx replay`, O2 `pmx evolve` and `pmx resume`, and O4 `pmx claim`, while every CLI file
of the earlier map belonged to another package: three commands had no owner and three packages would have
had to edit a file they do not own, which is why `cli_run.py`, `cli_evolve.py` and `cli_claim.py` exist.

### 13.1 The error taxonomy (`pmx.errors`, D1)

All errors derive from `PmxError(message, **context)` whose `str()` is the message followed by sorted
`key=value` pairs. Engine code never catches `PmxError` broadly; the gateway is the one exception and
only to build a fallback reply.

| Error | Raised by | Meaning |
|---|---|---|
| `SchemaError` | loader, runner, `pmx.engine.calendar.meta_kind` | a file or a payload fails its JSON schema; an instrument kind outside `INSTRUMENT_KINDS` read off a record or a meta (ruling R207) |
| `LeakError` | builder, observation builder | an instant after the freeze, or a future item reaching a view |
| `SealError` | `seal_dataset` | a reconstructed market in a dataset being sealed |
| `DatasetHashMismatchError` | `verify_dataset`, `run_backtest` | recomputed hash differs |
| `UnknownSubstreamError` | `pmx.rng` | unregistered substream name |
| `NonCanonicalValueError` | `canonical_json`, journal readers | float, set, CR, unsupported type |
| `JournalError` | `Journal`, `verify_journal` | seq gap, foreign run id, phase order breach, append after close |
| `ObservationTooLargeError` | observation builder | canonical size over `OBSERVATION_MAX_BYTES` |
| `FrozenMemoryError`, `MemoryFullError` | memory | write refused |
| `ClaimRefusedError` | claims | a second claim on the same `(dataset_hash, kind, provider, horizon_bars, genome_hash)`, or an `access.jsonl` line for it without a completed file (12.8, ruling R199) |
| `ProviderBlockedError` | importers | the ANJ block page (or any non-provider certificate) was served |
| `ProviderError`, `MalformedResponseError`, `BudgetExceededError`, `GatewayError` | gateway, importers | the impure edge failed; mapped to `RejectReason` at the gateway boundary |
| `InvalidConfigError` | every config `__post_init__`, `MarketMeta.__post_init__`, `genome_from_dict`, `make_agent`, `Workflow.__post_init__`, `resolve_sensor_set` | a config value outside its cap; a `MarketMeta` built with a kind outside the table, a construction error and not a file's (ruling R207); a genome without `tape`, with an unknown sensor or without a required one, a workflow outside 18.4's bounds, `window_days` above `WINDOW_DAYS_MAX`, a minute build naming a coarse source (amendment C1c) |
| `NotConfiguredError` | metaculus importer, live jobs, `pmx evolve` with `prompt_mutation` | an optional path used without its token or setting; prompt mutation before the live book holds `LIVE_REPLICATION_MIN_RESOLVED` resolutions (12.9, ruling R256) |
| `SensorAbsentError` | the sensed views of the observation builder (`SensedMarketView`, `SensedObservation`, `SensedBar`, `SensedHiveView`) | an agent read a field its sensor set did not buy (18.1, ruling R232); carries `field`, `unsensed` and `view`. Replaces the `SchemaError` E1's hook raised for want of a better fit |
| `RuleRefusedError` | `Rule.__post_init__`, `rule_from_dict`, the rule tester | a predicate outside the vocabulary or its bounds, a fourth predicate, a claim inconsistent with its kind, a rule whose family has no earlier `family_registered`, a duplicate of a rule already tested on the same `(dataset_hash, fit_fold, replicate_fold)`, or a family whose `n_screened` exceeds `RULE_PERMUTATIONS_MAX * FDR_Q_PPM // PPM_ONE = 1_000` (`reason = "family_too_large"`, 18.2, rulings R236, R238, R282, R284) |
| `FoldIntegrityError` | `verify_dataset`, `load_dataset`, `make_folds`, the rule tester, `claim` | the count-quantile cuts, the fold keys or the realised shares of the manifest disagree with what is recomputed from the metas, a cluster or `event_key` group spans two folds, a fold is empty, `Folds.rolling` would hold no pair, or a cohort row disagrees with the folds and facets recomputed (7.7, 18.5, rulings R248, R266, R277, R290) |
| `ShowcaseDatasetError` | `make_folds`, `run_generation`, `evolve`, `claim`, the rule tester, `pmx.features.matrix`, `run_backtest` | a `purpose: "showcase"` dataset reached a fold, a fitness value, a rule promotion or a claim (5.6, ruling R263), or a run named a showcase run in `memory_from_run_id` or `hive_from_run_id` (8.1, ruling R291); never a silent skip |
| `CohortRefusedError` | `pmx.cohorts.cohort_or_refuse`, the per-cohort leaderboard of 12.10, the `comparative` detector (R2d) | a cohort statement was asked of a cohort below `COHORT_MIN_TRAIN` or not `usable_for_paired_test` (18.5, rulings R266 and R283): refused before any measurement, never weakened to a smaller bar. Never raised by `claim`, which has no `--cohort` flag and reports every cohort as a `per_cohort` row |

### 13.2 Version constants (`pmx/__init__.py`, C0)

```python
__version__ = "2.0.0-dev"
ENGINE_VERSION = "2.0.0"        # bump when an existing run's journal bytes would move (R227)
CONTRACT_VERSION = "2.0"        # this document
OBS_VERSION = "obs.v2"; ACTIONS_VERSION = "actions.v2"; JOURNAL_VERSION = "journal.v2"
MARKET_SCHEMA = "market.v2"; NEWS_SCHEMA = "news.v1"; DATASET_SCHEMA = "dataset.v1"
INSTRUMENT_SCHEMA = "instrument.v1"; CASH_EVENT_SCHEMA = "cash_event.v1"          # amendment C1b, 17.9
SESSION_CALENDAR_SCHEMA = "session_calendar.v1"; FORECAST_SCHEMA = "forecast.v1"
RULE_SCHEMA = "rule.v1"; SENSOR_SCHEMA = "sensor.v1"; WORKFLOW_SCHEMA = "workflow.v1"   # amendment C1c, 18.8 (DS1 applies)
```

`run_started` carries `engine_version`, `contract_version` and `rng_algorithm_version`; a replay refuses a
journal whose `engine_version` differs from the running engine (exit code 2, message names both).

The bump trigger is a run, not a shape (ruling R227): a byte of a **journal a run has written** must move
for the same inputs. A change that moves the bytes of every future journal while no such run exists (the
eight `market_listed` fields of R201, the run id of a config that omits `horizons_bars`, the observation
bytes of a continuous run) versions nothing, because there is no journal a replay could refuse; the
contract fixture is a completed historical document and not a run (R202), and a gate's measurement runs
are evidence taken on one tree, not artefacts a later engine must reproduce. The first lot that applies
R213, R214, R217 or R221 (together with amendment C1c's `observation_built.sensors`,
`run_started.sensor_catalogue_hash`, `RunConfig.sensor_catalogue_hash` and the four `market_listed`
facets, ruling R274) moves what a future journal carries again and bumps both constants in the same
commit as R111 asks; from the first run a later engine is expected to replay, every byte movement bumps
again, and a replay's exit-2 refusal is what the constant buys. Amendment C1c moves no byte of a journal a
run has written and leaves both constants (ruling R275).

---

## 14. Wave plan cross-reference

| Plan package | Sections of this contract it implements | Contract names it must produce |
|---|---|---|
| C0 | all; 13; 15 | this document, the five schemas, `tests/test_architecture.py`, `tests/test_contract_schemas.py` |
| D1 | 1, 2, 4.1 (consumer), 7.2, 7.3, 7.8, 7.10, 7.13, 13.1, 13.2, 17.2 (`pmx.data.sessions`: `in_session`, `next_bar_ms`, `load_calendar`, the synthesised `continuous` calendar, ruling R174, applied by gate G2 with the `pmx.types` names of 17.9) | `pmx.types` (every constant and dataclass named here, `brier_micro` and `neg_ln_micronats` of 1.2 and 1.3 (ruling R217), plus `AgentReply`, the `Gateway` protocol, `MarketMeta`, `Dataset`, `MarketQuality`, `RESEARCH_UNIT_COST`, `PHASE_ORDER`, `market_set_hash`, `CATEGORIES`, `LEXICON_COUNT`, `Descriptors`), `pmx.errors`, `pmx.data.schema` (`SCHEMA_DIR`, `load_schema`, `schema_path`), `pmx.data.loader` (`load_dataset`, `load_market`, `seal_dataset`, `verify_dataset`), `pmx.data.migrate_v1.migrate_v1`, `data/demo_v1/` |
| D2 | 7.2 (Kalshi mapping), 7.4 (shard exclusion), 7.11, 7.12, 8.8 (fee ids) | `pmx.data.importers._http.HttpClient` (7.11 verbatim), `pmx.data.importers.kalshi.import_kalshi`, `list_open_kalshi`, `KALSHI_EXCLUDED_SERIES` |
| D3 | 7.2 (Manifold mapping), 7.3 (comments), 7.12 | `import_manifold`, `list_open_manifold`, `pmx.data.news.manifold_comments.fetch_comments` |
| D4 | 7.2, 13.1 (`ProviderBlockedError`) | `import_polymarket`, `PMX_HTTP_PROXY` |
| D5 | 5.5, 7.1 (asof rule), 7.3, 7.6, 7.12, 10.5 (lexicons) | the four fetchers of 7.12, `pmx.data.news.linker.link_items`, `src/pmx/lexicons/stopwords.v1.json`, `src/pmx/lexicons/paraphrases.v1.json` (`{"paraphrases": [str, str, str]}`), the 12 `src/pmx/lexicons/<category>.v1.json` |
| D6 | 5.2, 7.1, 7.4, 7.5, 7.7, 7.8 | `pmx.data.resample.bars_from_trades`, `pmx.data.builder.build_dataset`, `BuildConfig`, `pmx.cli_data` |
| D7 | 4, 6, 9.1 | `pmx.rng` (all names of 6.1), `pmx.journal` (`canonical_json`, `Journal`, `read_journal`, `write_journal`, `verify_journal`, `iter_bars`, `filter_events`, `journal_hash`, `JOURNAL_ENCODING`, `JOURNAL_NEWLINE`), the event dataclasses of 9.2 and 9.4 as `pmx.journal.events.*` |
| E1 | 5.3, 5.4, 7.9, 8.3, 16.3 (the leak list of 7.9 gains every cluster-derived name of 16.3, and the poisoned-future test gains one of each), 17.2 (the run calendar as the union of the instruments' bars, `open`/`tradable`/`last_bar` for a continuous instrument, `MarketView.kind` and its scale fields, `hours_to_next_bar`, `underlying_id`, `twins` and `cash_events` filled on D1's defaulted fields (ruling R188), `MarketView.close_at_ms = 0` and `tradable = open(i, t)` on a continuous instrument (ruling R181), `BarSlice.closing_ids`, `Calendar.last_bar`, `next_bar` and `prev_bar` (ruling R187); the poisoned-future test gains a `CashEvent` whose application bar has not completed, an applied one that must surface, a `delisted_at_ms`, a `last_bar` and an unresolved `price_realised_ticks`) | `pmx.engine.calendar.Calendar` and `BarSlice`, `pmx.engine.observation.build_observation`, `render_observation_json` (the three signatures of 8.3, literal) |
| E2 | 8.5 to 8.9, 16.1, 16.2, 17.1, 17.3, 17.4 (the generalised netting and the liability model, `apply_cash_events`, `force_flat`, `event_fill`, the half-spread floor, the `bad_size` check, every fee model and `CARRY_SCHEDULES`, the `calendars` argument and the per-instrument queue of ruling R174, `applies_at` and the entitlement rule of ruling R175, the engine events' `t_ms` of ruling R176, the `carry` event of ruling R177, the debit balance of ruling R179, `slippage_ticks`, `clamp_price` and the continuous `check_envelope` case of ruling R173, the per-kind accounting property tests) | `pmx.engine.liquidity` (the `LiquidityModel` protocol, `Fill`, `LiquidityOrder`, `LiquidityMarketView`, `ObservedFlow`, `ENVELOPE_BREACHES`, `check_envelope`, `finalise_fill`, `truncate_for_cash`, `cap_milli`, `allocate_cap`, `envelope_bounds`, `MILLI`, `LIQUIDITY_MODELS`, `make_liquidity`, and the `historical` implementation, all literal in 16.1), `pmx.engine.execution.Execution` (`place`, `pending_market_ids`, `execute_bar`, `settle`, `mark`, `portfolio`, `position`, the constructor of 8.6), `pmx.engine.fees.FEE_SCHEDULES`, `fee_cents`. It emits no `settled` and no `settlement_applied` (section 9.3) and needs nothing from `pmx.scoring` |
| E3 | 1.3, 12.1, 12.2, 17.5 | `pmx.scoring` (`brier_tw_micro`, `horizon_buckets`, `horizon_bucket_of`, `skill_micro`, `log_micronats`, `pmv_bp`, `logit_milli`, `unlogit_ppm` (12.1, ruling R217; `brier_micro` and `neg_ln_micronats` are `pmx.types`'), and amendment C1b's `directional_brier_micro`, `pinball_micro`, `directional_skill_micro`, `pinball_skill_micro`, the per-instrument-and-horizon plain-mean aggregation of ruling R191; `default_horizons_bars` is `pmx.types`', ruling R188), `pmx.metrics.calibration.calibration_table` (per `(kind, horizon)` slice, `n_yes_x2` and `CalibrationBinView.n_yes_x2`, ruling R194); asserts the random-walk zero-skill identity and the tie rule |
| E4 | 12.4, 16.3, 17.6 | every name of 12.4, with `block_key(market, *, cluster_id: str | None = None)` (ruling R118): the keyword-only argument ships in wave 2 and R1b fills it in wave 7, so no signature is widened later; `permutation_null(..., realised_signs=None, bar_keys=None)`, the within-week permutation of `realised_sign` (ruling R190) |
| E5 | 8.2, 9.2, 9.3, 9.5, 12.3, 12.5, 12.10, 12.11, 16.1, 16.2, 17.3, 17.5, 17.6 (the settle-phase drive of `apply_cash_events` and `force_flat`, `forecast_resolved` and `instrument_closed`, the reference and realisation lookups, the carried horizon statements, the per-horizon hive writes, `kind`/`horizon_bars`/`unit_key` on every row, `exposure_by_kind`, the `(instrument, week)` units) | `pmx.engine.runner.run_backtest` and `replay` (12.11, literal, including the **required** keyword-only `liquidity`, ruling R139), the decision-latency plumbing of 16.2 (`place` in `decide`, `execute_bar` driven over `pending_market_ids(t_ms)` and draining the previous bar's queue, `decided_at_ms` in the two execute-phase events), `pmx.metrics.projection.project` with `RunProjection`, `PerMarket`, `AgentResult`, `MarketResult`, `RunHandle`, `performance`, `behavioral.descriptors`, `leaderboard.build`, `pmx.store`, `pmx.cli_run` |
| A1 | 10.1, 10.2, 10.5, 16.5, 17.7 (the `random_walk` baseline and the `carry`, `basis`, `pairs`, `vol_regime` and `calendar` families; the one-line tick generalisation of `trend`, `revert`, `breakout` and `volume`) | `pmx.agents.protocol` (`Agent`, `Genome` with the fifth component `card: ModelCard | None` of ruling R119, always rendered by `to_dict()` and `null` for every family but `torch_policy`, `GeneSpec`, `FamilySpec`, `ResolutionEvent`, `Explanation`), `pmx.agents.registry` (`FAMILIES`, `DEFAULT_ROSTER`, `genome_from_dict`, `make_agent`, `mutate`, `crossover`, `structural_mutate`, `random_genome`), the eleven family modules of 10.5 except `stacker` |
| A2 | 10.3 | `pmx.agents.memory.AgentMemory` (the constructor of 10.3, literal) |
| A3 | 10.4 | `pmx.agents.hive.RunHive` (the constructor of 10.4, literal), `compute_reputation` |
| A4 | 10.5 (stacker, ensembles) | `stacker`, `top_k_extremized_mean`, `live_coop` |
| A5 | 11 | every name of 11.1 to 11.4, `configs/models.json`, `llm/prompts/` |
| A6 | 11.5 | `pmx.llm.contamination.audit`, `is_clean`, `load_contamination` (11.5, literal), `pmx.cli_audit` |
| O1 | 12.6 (objective), 12.7, 12.11 | `make_folds`, `open_sealed_test` (12.7, literal, including its `sealed_test_opened` event and its `access.jsonl` line), `pmx.optimizer.tournament.run_generation` with `GenerationResult` |
| O2 | 9.4, 10.1 (operators use), 12.5 (bins), 12.11 | `pmx.optimizer.evolution.evolve`, `resume`, `EvolutionConfig`, `pmx.optimizer.archive.Archive`, `pmx.cli_evolve` |
| O3 | 12.9 | `worst_markets`, `apropose_patch`, `ab_on_validation`, `promote` |
| O4 | 12.6 (bar), 12.8 | `pmx.optimizer.claims.claim`, `claims/` and `claims/access.jsonl`, `pmx.cli_claim` |
| U1 | 9.5 (read), 12.10, 12.12 | `pmx.api.app.create_app`, every route of 12.12, SSE, worker, `web/src/api.ts`, `web/src/types.ts` |
| U2, U3 | 8.3 (what the UI may show is what an observation may show, plus the outcome after the cursor passes `resolved_at_ms`), 12.12 (consumer) | the views |
| U4 | 13.2, PRD 7.3 | `pmx.cli`, `run.bat`, `README.md`, `docs/BUILD_STATE.md` |
| L1 | 4.3 (`forecast_hash`), 7.12 (`list_open_*`, `OpenMarket`), 9.5 (`live/` line shapes) | `pmx.live.*`, `pmx.cli_live` |
| C1b | 17 (all), 15.9, and the in-place amendments of 1, 5.2, 5.3, 7.2, 7.4, 7.6, 7.8, 7.9, 8.1, 8.2, 8.4 to 8.9, 9.2, 9.3, 10.3, 10.4, 12.1 to 12.3, 12.6 to 12.8, 12.10, 12.11, 12.12, 13, 14, 16.1 | this amendment: `src/pmx/schemas/instrument.v1.json`, `cash_event.v1.json`, `session_calendar.v1.json`, `forecast.v1.json`, the widenings of `journal.v2.json` and `actions.v2.json`, rules 10 and 11 of `tests/test_architecture.py`, the fixtures `instrument.binance-btcusdt-perp.json`, `instrument.xnas-aapl.json`, `cash_events.sample.json`, `session_calendar.xnys.json`, `forecast.sample.json` under `tests/fixtures/contract/` |
| F1 | 17.1, 17.3 (funding events), 17.7 | `pmx.data.importers.binance.import_binance`, `kraken.import_kraken`, `coinbase.import_coinbase`, `bybit.import_bybit` (the keyword-only shape of 17.7), `twins` by symbol mapping, the funding history as `CashEvent`s |
| F2 | 17.1, 17.3 (dividend, split, roll events), 17.7 | `pmx.data.importers.yahoo.import_yahoo` (vendor `yahoo`, throttle, cache, `CashEvent`s from the chart `events`, roll detection with `roll_source = "vendor"`), `frankfurter.import_frankfurter`, `ecb.import_ecb` |
| F3 | 7.3 (the three new sources and two kinds), 17.7 | `pmx.data.news.edgar.fetch_edgar`, `fred.fetch_fred` (ALFRED vintages), `release_calendar.load_releases`, `cboe.fetch_vix`, `src/pmx/data/calendars/releases.v1.json`, the four `src/pmx/lexicons/fin_<topic>.v1.json` |
| F4 | 17.2 (the static exchange calendars), 7.4 (`kinds`) | `src/pmx/data/calendars/*.json` (`xnys`, `xnas`, `arcx`, `cme_globex`, `fx_weekly`, generated for the window through D1's `pmx.data.sessions`, ruling R174; `continuous` is never a file, ruling R185), `pmx.data.universe_finance` (the dated universe), the `--kinds` option through the hook D6 exposes |
| G3b | 17 (all), PRD v4 section 7 | `tests/e2e/test_e2e_1b_multi_asset.py`; the first multi-asset dataset at an hourly grid (AC-21) with its numbers in `docs/BUILD_STATE.md` |
| R2f | 16.4, 17.6 | `pmx.analysis.cross_domain` (binary versus underlying, funding and basis, cross-venue crypto, macro releases with ALFRED clocks, post-filing drift), `tests/e2e/test_e2e_2b_cross_domain.py` through gate G8 |
| C1 | 16 (all), 13, 14, 15.8 | this amendment: `src/pmx/schemas/cluster.v1.json`, `opportunity.v1.json`, `features.v1.json`, `model_card.v1.json`, the section 16 interfaces, the module map rows above, rules 7 to 9 of `tests/test_architecture.py`, the fixtures under `tests/fixtures/contract/` |
| R1a | 16.3 (the universe block of the manifest) | `pmx.data.universe`, `pmx data stats` |
| R1b | 16.3 | `pmx.data.clusters` (`EventCluster`, `Constraint`, `MatchReason`, `RE_CLUSTER_ID`, `RE_CONSTRAINT_ID`, `constraint_residual_ppm`, `build_clusters`, `load_clusters`), `clusters/clusters.json` and `clusters/overrides.json` |
| R1c | 16.1 | the `calibrated_impact` implementation inside E2's `pmx.engine.liquidity`, `pmx.data.impact` (the calibration projection and its manifest block) |
| R1d | 7.1, 16.3 (the UI cluster view) | the hourly build option in `pmx.data.builder`, `web/src/components/clusters/**` |
| R2a R2b R2c R2d | 16.4 | `pmx.analysis.news_lead`, `divergence`, `logic`, `comparative`; each emits `OpportunityEvent`s under `opportunity.v1.json` |
| R2e | 16.4, 12.12 (the analysis routes) | `pmx.analysis.report` (the opportunity map, `RE_OPPORTUNITY_ID`), `pmx.cli_analyze`, `pmx.api.routes_analysis`, `web/src/components/opportunities/**` |
| R3a | 16.5 | `pmx.features.spec` (`FeatureSpec`, `FEATURES`, `FEATURES_VERSION`, `features_hash`), `build`, `view.float_view`, `quantise.ppm_from_unit` and `position_from_unit` |
| R3b | 16.5 (the embedding block) | `pmx.data.embeddings` |
| R3c R3d | 16.5 | `pmx.learn.*`, the `ModelCard` of `model_card.v1.json`, `pmx.cli_learn` |
| R3e | 16.5, 10.1 | `pmx.agents.families.torch_policy` (the one legal float site of ruling R120) |
| R4a R4b R4c R4d | 16.1 (the envelope), 16.4 (the robustness gap's events) | `pmx.adversary.*`, `pmx.cli_adversary`; `adversary_mm` passes E2's `check_envelope` under a property test |
| R5a R5b R5c | 16.4 (the allocator's inputs), 16.5 | `pmx.portfolio.*`, `pmx.cli_portfolio`, `pmx.learn.llm_finetune` |
| R6a R6b | 16.4 | `pmx.live.opportunities`, the live and portfolio views |
| G6 | 16.6, PRD v3 section 9 (rung 0) | `tests/e2e/test_e2e_0_base.py`: build, run, replay and claim on fixtures (ruling R137) |
| G7 G8 G9 G10 G11 | 16 (all), PRD v3 section 9 | `tests/e2e/test_e2e_<n>_<name>.py`, one per rung; the gate of a rung runs `tests/e2e/` in full and fails when a delivered rung's file is absent, so a missing test cannot pass as an empty directory |

### 14.1 Decisions a reviewer should challenge

Judgement calls not dictated by the PRD, cheap to change now and expensive after wave 1:

| # | Decision | Where | Alternative |
|---|---|---|---|
| D-1 | Cash stays in cents with notional rounding against the agent (`cost_cents` up, `proceeds_cents` down) | 1.2, 8.5 | cash in hundredths of a cent, exact at the price of every UI number |
| D-2 | **Superseded by amendment C1 (ruling R107): the alternative was taken.** An action decided on bar `t` fills at the open of bar `t + interval_ms`. The original decision (decide on completed bars, fill at the current bar's vwap) stood from wave 0 until C1 | 5.3, 5.4, 8.2, 8.6, 16.2 | the original: fill at the deciding bar's own vwap |
| D-3 | Density filter default `250` permille (one traded bar per four days) instead of the PRD's one per day | 7.4 | keep 1000 and accept a much smaller Manifold set |
| D-4 | `trivial` means "never in doubt from the first bar" (the PRD's parenthesis is read as a slip) | 7.5 | the PRD's literal "never left [500, 9500]", which tags the hard markets |
| D-5 | `ruin_floor_cents` default `1_000` (1 percent of bankroll), not zero | 8.7 | zero, which almost never fires under cash-limited trading |
| D-6 | The three v1 archetypes no gene expresses (`contrarian`, `anchor`, `sharp`) ship as a `legacy` family excluded from evolution; `stubborn` is `follower(0, 0)` and `momentum` is `trend`, both gene-expressed | 10.5 | widen `follower.shrink_permille` to negative values |
| D-7 | Three archive axes (turnover, contrarian, abstention), 48 cells | 12.5 | five axes and a much sparser grid |
| D-8 | Deflated bound by normal approximation with Bonferroni `alpha / K` | 12.4 | empirical quantile with `B` scaled to `K` |
| D-9 | LLM lessons are produced by the next bar's single call, keeping `learn` pure | 8.2, 11.3 | a second call at settlement (doubles cost) |
| D-10 | The journal digest is SHA-256, the seed derivation BLAKE2b | 4.3 | one algorithm for both |
| D-11 | Every news fetcher goes through `data/importers/_http.py` | 13 | let `data/news` open sockets and widen the architecture rule |
| D-12 | `follower(1000, 0)` is the baseline in every slice; `skill` is paired against it per market | 12.1 | pair against the fixed `500_000` forecast |
| D-13 | A `reconstructed` market is exempt from the volume rules of 8.6 rather than carrying a synthetic volume, so the demo pack is tradable and PRD 3.3's `volume_milli = 0` stands | 8.6, 7.10 | stamp `DEMO_BAR_VOLUME_MILLI` on every migrated bar and let the cap and the slippage apply to a number the source never had |
| D-14 | Only a bar entirely inside the trading window is tradable (`t + interval_ms <= close_at_ms`), so the close-day tape cannot fill anything | 5.3, 8.6 | keep `t < close_at_ms` and accept fills at post-close, post-outcome prices |
| D-15 | Part 2 of the bar requires `n_markets_traded >= 60`, so a five-market trader cannot clear it with 55 variance-free zeros; the verdict stays `no_demonstrated_edge` rather than becoming `insufficient_n` | 12.6 | make either shortfall `insufficient_n`, which hides a real forecasting result behind a trading one |
| D-16 | `K` is the max of the evolution count, the store count and the prior-claim count, computed by `claims.py` | 12.6 | trust `candidates_evaluated_cum` as passed in |
| D-17 | The five schemas live in `src/pmx/schemas/`, not at the repository root | 7.13, 13 | keep them at the root and give D1 a repository-relative path that no installed package can resolve |

---

## 15. Rulings

The gate that closes a wave records here every decision it took to reconcile the packages' contract
issues: one ruling per entry, numbered `R1, R2, ...`, naming the section it amends, the packages it
affects, and whether it moves a journal byte (those require a bump of `ENGINE_VERSION`). A ruling is
written in the same commit as the code that implements it. The section starts empty.

### 15.1 Wave 0 (C0)

Three independent critics attacked the first draft; the arbiter resolved every finding in the text. Each
ruling below names the section it amended. Nothing here moves a journal byte of an existing run, because
no run exists: `ENGINE_VERSION` stays `2.0.0`. Two findings were resolved **against** the fix the critic
proposed, and both say why (R41 and R71).

| # | Ruling | Sections |
|---|---|---|
| R1 | Rule 3's list of legal float sites now includes the USD and timeout fields of `GatewayConfig` and `BudgetTracker`, which declared five more floats than the rule allowed; "the one legal float" is deleted from 11.1 | preamble, 11.1 |
| R2 | `round_half_up_decimal` added; no formula in this document uses `/` or a float scale literal; **every ratio is `0` when its denominator is `0`** and an empty bin reports `n: 0` with every field `0`, because six normative formulas were reachable with a zero denominator on the common path | 1.2, 12 |
| R3 | The claim that the migrated pack "reproduces v1 Brier values to the micro-unit" is false and is replaced: every migrated bar close equals the v1 cent price times 100, and the life-average Brier deliberately differs from v1's control-point average, which E3 pins (PRD 4.5) | 1.4 |
| R4 | The fee-schedule regex accepts the shipped `demo-zero`, which the old regex refused while every demo market carries it | 2, 8.8 |
| R5 | A claim id carries its provider (`c-<dataset_hash[:8]>-<provider>-<genome_hash[:16]>`), so the two provider claims of one genome no longer collide on one file name | 2, 12.6, 12.8 |
| R6 | The `lf-` live-forecast regex is filled in, since section 2 says every regex there is a constant | 2 |
| R7 | A `wce` news id names the **page day** `D` while its file is `news/<day_start_ms(published_at_ms)>.jsonl`, which is `D + 1`; the loader validates the file day | 2, 7.1 |
| R8 | A run id is unique per `(dataset, seed, config, market set, fold)`: `fold` and `market_ids_hash` enter `RunConfig`, so a generation's training and validation runs no longer share a directory and a journal | 2, 8.1 |
| R9 | `tradable(m, t)` requires `t + interval_ms <= close_at_ms and not settles(m, t)`: only a bar entirely inside the trading window can fill, so the close-day and election-night tape can no longer be traded after the outcome was known | 5.3, 8.6 |
| R10 | One grid per run: `config.interval_min` must equal the manifest's and every market's, else `InvalidConfigError`; there is no run-time resampling and an hourly claim is a second dataset | 5.3, 7.8 |
| R11 | On a market's first bar no bar is completed, so `last_price_bp = market.first_price_bp`, `bars = ()`, `best_bid_bp = best_ask_bp = None`, and the market's own baseline forecast is the same value; `first_price_bp` joins `MarketView` | 5.4, 8.3, 12.1 |
| R12 | A `forecast` or `resolution` hive entry is stamped `bar_of(resolved_at_ms) + interval_ms`, not `resolved_at_ms`: the old stamp leaked every open forecast on a venue that settles on the grid and hid every entry for the whole run on a venue that does not; `write_forecast` and `write_resolution` therefore take `interval_min` | 5.4, 9.2, 10.4 |
| R13 | Every memory record carries `written_at_ms` and `Memory.view(now_ms=...)` filters on it, closing the one channel into an observation that had no as-of filter; the poisoned-future test injects a memory record stamped after `now_ms` | 5.4, 7.9, 10.3 |
| R14 | `run_backtest` receives its `RngTree` as a required keyword-only `tree`, with one literal signature in 12.11; the plan's `seed` positional is superseded and 6.2's "never constructs one" is now satisfiable | 6.2, 12.11, 14 |
| R15 | The demo pack is exempt from the twelve-month window and the freeze checks, and its window, freeze and month edges are derived from its own markets | 7.1 |
| R16 | A `wikipedia_asof` item carries `revid` and `asof_day`, D5 fetches one snapshot per 7 days of life and none at or after `bar_of(resolved_at_ms)`, and the loader refuses an item published after its `asof_day`: a current revision stamped with an early date was undetectable | 7.1, 7.3, news.v1.json |
| R17 | `wiki_subjects` is a new field for the market's article titles (spaces, capitals, colons kept) and `tags` keeps its slug pattern; the linker compares against `wiki_subjects` | 7.2, 7.6, market.v2.json |
| R18 | The `Market` field `last_price_bp` is renamed `final_price_bp`: the name meant two opposite things, and `MarketView(last_price_bp=market.last_price_bp)` was a leak no named test would have caught | 7.2, 7.9, market.v2.json |
| R19 | `Market.bar_at`, `Market.bars_before`, `MarketMeta`, `MarketQuality` and `Dataset` are declared, because 8.6, 12.4 and 12.7 already called them by name | 7.2 |
| R20 | The Manifold mapping is written with `Decimal` and `round_half_up_decimal`: it called the two-argument `round_half_up` with one argument, twice, and multiplied by a float | 7.2, 1.2 |
| R21 | `BuildConfig` is declared field by field and `manifest.filters.removed` is pinned to exactly ten keys, every one always present | 7.4, dataset.v1.json |
| R22 | The linker's score is `round_half_up(600 * shared_links, max(1, n_links)) + (400 * keyword_overlap) // 1_000`, which lands in `[0, 1000]`; the old spelling used float division and reached 400 600 against a schema cap of 1 000 | 7.6, news.v1.json |
| R23 | D5 ships exactly `stopwords.v1.json`, `paraphrases.v1.json` and one lexicon per category, so `LEXICON_COUNT = 12` is a constant and `newsbayes.lexicon_id` has a range A1 can write without counting D5's files | 7.6, 10.5, 13, 14 |
| R24 | An hourly headline claim needs a dataset built at `interval_min = 60`, with its own hash and folds | 7.8 |
| R25 | The leak list gains `final_price_bp`, `fold` and any memory record newer than `now_ms` | 7.9 |
| R26 | New section 7.10 states the six v1 migration identities the schema test asserts, which the test cited before they existed | 7.10 |
| R27 | New section 7.11 declares `HttpClient` in full (throttle unit, cache key and layout, backoff, User-Agent, proxy), which four wave-1 packages had to share and none could see | 7.11, 13, 14 |
| R28 | New section 7.12 declares one shape for every importer and fetcher, adds `OpenMarket` and `list_open_kalshi` / `list_open_manifold` for L1, and states that D6 alone writes files | 7.12, 14 |
| R29 | New section 7.13 moves the five schemas to `src/pmx/schemas/` and declares `SCHEMA_DIR`, `load_schema` and `schema_path`: A5 hands `actions.v2.json` to the CLI at run time and a repository-root path does not exist in an installed `pmx` | 7.13, 13 |
| R30 | `RunConfig` gains `hive_forecasts`, `markets_per_obs_max`, `research_budget_by_agent`, `memory_from_run_id`, `hive_from_run_id`, `contamination_hash`, `fold` and `market_ids_hash`, and `to_dict()` widens to `dict[str, object]`; the runner raises `LeakError` when the memory source run ended after this run starts | 8.1, 10.3, 12.7 |
| R31 | `RESEARCH_UNIT_COST`, `RESEARCH_PENALTY_UNITS`, `HIVE_FORECASTS_MAX` and `MARKETS_PER_OBS_MAX` are named constants; a research request has a price and a budget breach is journaled, not guessed | 8.1, 8.4 |
| R32 | The `open` phase emits `market_listed` and `market_priced`; the `close` phase's event list gains `order_expired`, which ruin already produced | 8.2, 9.2 |
| R33 | A ruined agent is skipped in `observe` and `decide` but still receives `forecast_recorded(carried=true)` on every open market, so dying cannot drop the markets it was losing on and every agent is scored on the same bars | 8.2, 8.7, 12.1 |
| R34 | The write order inside the `hive` phase is fixed (forecasts, resolutions, reputations, lessons), so entry ids are deterministic | 8.2, 10.4 |
| R35 | `Calendar`, `BarSlice`, `build_observation` and `render_observation_json` are declared literally, so E5 can call E1 blind | 8.3, 14 |
| R36 | `HiveView.forecasts` gains a cap (`hive_forecasts`) and a scope (settled markets, the agent's open categories), and `live_forecasts` is renamed `prev_bar_forecasts` with `bar_ms == now_ms - interval_ms`: the old field was self-contradictory, order-dependent and unbounded at 8 MiB | 8.3, 10.4 |
| R37 | More than `markets_per_obs_max` open markets is a deterministic selection, not a schema failure: the actions cap of 200 is never reachable | 8.3, 8.4 |
| R38 | The clock test is structural (a key-set check plus a bar-count check plus the as-of price identity), because an integer scan cannot pass on legal data where `close_at_ms == resolved_at_ms` | 8.3 |
| R39 | A `hold` never produces an order, a `target` equal to the current position produces none either, and a second action on one market in one bar is `duplicate` whatever its kind with the first occurrence winning | 8.4 |
| R40 | Step 0 of the fill model: an order on a bar that is not tradable is `order_rejected(not_tradable)` | 8.6 |
| R41 | A `reconstructed` market is **exempt** from the volume rules (no cap, no slippage, `vwap` pricing), rather than carrying a synthetic `DEMO_BAR_VOLUME_MILLI` as one critic proposed: PRD 3.3 pins `volume_milli = 0` on migrated bars, and inventing a volume the source never had would also invent a cap and a slippage. Either way the demo pack becomes tradable, which it was not (decision D-13) | 8.6, 7.10, 14.1 |
| R42 | A limit fill defines `base_price_bp = fill_price_bp` and `slippage_bp = 0`, does not cross as `no_cross`, and `unfilled_reason` has a precedence (`zero_volume`, `no_cross`, `volume_cap`, `cash`) | 8.6 |
| R43 | `Execution`'s constructor and six methods are declared literally, and `settle` returns the per-agent cash deltas | 8.6, 14 |
| R44 | Marking uses `mark_price_bp`, the close of bar `t` itself, explicitly distinct from the observation's `last_price_bp`; the two readings gave two different equity and ruin series | 8.7, 8.2 |
| R45 | `settled` and `settlement_applied` move from E2 to E5, and their Brier, `n_bars`, `n_forecast_bars`, `life_mean_price_bp` and `realised_pnl_cents` fields are defined: `Execution` never sees a forecast and could not have computed them | 8.7, 9.3, 14 |
| R46 | `PHASE_ORDER` is `pre, open, observe, decide, execute, settle, learn, hive, close, generation, post`; `bar_ms` is `0` for `run_started`, `sealed_test_opened` and every evolution event and `t1_ms` for `run_ended`; `seq == 1` is `run_started` **or** `evolution_started`. Three sources disagreed and `verify_journal` rejected the contract's own evolution fixture twice | 9.1, 9.4 |
| R47 | `run_started` gains `folds`, `memory_from_run_id`, `memory_hash`, `memory_from_run_t1_ms` and `contamination_hash`, so a run's provenance is in the journal and not only in prose | 9.2, journal.v2.json |
| R48 | `market_listed` and `market_priced` are added as observed inputs, because `pmx replay` could not rebuild the horizon buckets, `pmv_bp`, `contrarian_bp`, the block keys or the per-category and per-fold rows from the journal alone, and E5 would have shipped a projection that reads the dataset | 9.2, 9.5, 12 |
| R49 | `sealed_test_opened` is added and `open_sealed_test` appends it plus one line to `claims/access.jsonl` before returning any id: a peek that aborted left no trace anywhere | 9.2, 12.7 |
| R50 | AC-5 is behavioural: with `run_started` excluded, at least one `forecast_recorded.prob_ppm` must differ for a hive reader and for a memory reader, and the skill delta comes from the two `results.json`. Comparing hashes alone passed even when neither switch changed a decision | 9.2 |
| R51 | The evolution envelope matches the schema (`pre`, `generation`, `post`, `bar_ms = 0`) and `candidates_evaluated_cum` is non negative in both events, so a generation that validated nothing is legal | 9.4, journal.v2.json |
| R52 | `manifest.json` carries `memory_snapshots`, `agent_snapshots`, `hive_snapshot` and `memory_hash`, and the two `live/` line shapes are declared: the memory chain, the fold carry-forward and the claim freeze all depended on fields no file had | 9.5, 10.3, 12.7 |
| R53 | `Genome` gains `members`, always present in `to_dict()`: the stacker's "members it is composed with" had no representation, its only formula divided by zero, and A4's done-when was unreachable | 10.1, journal.v2.json |
| R54 | `FamilySpec`, `FAMILIES`, `DEFAULT_ROSTER`, `make_agent`, `genome_from_dict`, `mutate`, `crossover`, `structural_mutate` and `random_genome` are declared, and `reset_permille` moves into `EvolutionConfig`, so O2 can drive A1's registry blind | 10.1, 12.11 |
| R55 | The `Agent` protocol gains `kind`, `model` and `knowledge_cutoff_ms`, which `run_started.roster` journals and the runner had no path to | 10.2, 9.2 |
| R56 | `AgentMemory`'s constructor is literal, the memory persistence mechanism is spelled out, and the last horizon bucket is `< 2` so the settlement-lag bars (where `days_to_close` is negative) have a bucket | 10.3, 12.1 |
| R57 | `RunHive`'s constructor is literal, `write_forecast` and `write_resolution` take `interval_min`, and a table fixes the scope and cap of every `HiveView` field | 10.4, 8.3 |
| R58 | Three reading rules head the family table: every belief is in ppm, a `_bp` gene is a threshold and never a multiplier, every window is clamped to the available completed bars and a family with fewer than two bars states the price and holds. Every family raised `IndexError` on the first bars of every market | 10.5 |
| R59 | `lean_bp_per_bp` becomes `lean_permille` (the old name was a factor of 100 from reproducing v1's `momentum`), `longshot_fade_bp` becomes `longshot_fade_permille`, `conviction_per_vol` becomes `conviction_permille`, and `calibrator` loses its `bins` gene because the ledger is fixed at ten deciles | 10.5, 10.3 |
| R60 | The stacker instantiates and runs its own `members`, uses the hive only for the reputation weights, falls back to their unweighted mean when no member has a reputation, and `live_coop` only adds previous-bar forecasts as extra members | 10.5 |
| R61 | The roster is eight literal genomes; `stubborn` is `follower(0, 0)` and `momentum` is `trend(5, 600, 1)`, so only `contrarian`, `anchor` and `sharp` are `legacy`. The old paragraph retracted itself mid-sentence, delegated the roster to `registry.py` and was wrong in both directions (decision D-6 corrected) | 10.5, 14.1 |
| R62 | `AgentReply` and the `Gateway` protocol are declared in `pmx.types` and re-exported by `pmx.gateway.protocol`: `agents/protocol.py` and `engine/runner.py` must annotate them and rule 1 of the architecture test forbids them from naming `pmx.gateway` at all | 11.1, 10.2, 14 |
| R63 | `LlmForecaster` is the one LLM agent, family `llm`, constructed by its caller and registered in no `FAMILIES` row (which would make `registry.py` import `pmx.llm`) | 11.4 |
| R64 | `contamination.json` enters the run through `RunConfig.contamination_hash`, `run_started` and the claim (with `n_clean` and `clean_market_ids`), and `is_clean` / `load_contamination` are pure functions the leaderboard receives rather than imports | 11.5, 8.1, 12.8 |
| R65 | Section 12 opens with the zero-denominator rule and E5's test that a `follower(1000, 0)`-only run produces a complete leaderboard row of zeros rather than a `ZeroDivisionError` | 12, 12.3, 12.5 |
| R66 | The market baseline `p_i` reads `market_priced.last_close_bp` (so the `skill(market_follower) == 0` identity holds on the first bar too), the `0d` bucket is `< 2`, the log score is spelled without a float, and PMV over no eligible bar is `0` | 12.1 |
| R67 | `abstention_ppm` is redefined as "ended the bar flat and placed no order", `explicit_abstain_ppm` is added beside it, and `n_markets_traded` and `n_markets_open` join the row: the old definition read `0` for the most silent agent | 12.3, 12.5, 12.10 |
| R68 | `bootstrap_lower_bound` on fewer than two blocks returns a degenerate `Interval` instead of raising | 12.4 |
| R69 | `n_markets_open` is defined once (distinct markets that appeared in the agent's observations) and lives in `AgentResult`, so E5 and O2 bin the same integer | 12.5, 12.11 |
| R70 | The research budget adjustment is a rule, not an invitation: no improvement in `skill_lb_micro` with `research_units_spent > 0` costs `RESEARCH_PENALTY_UNITS` next generation, applied through `research_budget_by_agent` | 12.6, 8.1, 9.4 |
| R71 | Part 2 of the bar requires `n_markets_traded >= CLAIM_MIN_MARKETS` **inside part 2**, rather than making either shortfall `insufficient_n` as the critic proposed: an agent that trades five markets and abstains from 55 cleared a positive lower bound on 55 variance-free zeros, but a forecaster that never trades deserves `no_demonstrated_edge` with `parts.pnl = false`, not a verdict that hides its forecasting result (decision D-15) | 12.6, 12.10, 14.1 |
| R72 | `K` is the maximum of `candidates_evaluated_cum`, the distinct genome hashes ever scored against this dataset in `pmx.store`, and the prior claims on it plus one; it is computed by `claims.py`, never passed in, and all three counts are recorded. It used to be the number the claimant wanted it to be | 12.6, 12.8 |
| R73 | `claims/` is tracked (only `claims/*.tmp` is ignored), each claim chains `prev_claim_sha256`, and a claim whose `(dataset_hash, provider, genome_hash)` appears in `access.jsonl` without a completed file is refused | 12.7, 12.8, 13, .gitignore |
| R74 | The claim record gains `n_markets_traded`, the three candidate counts, `contamination_hash`, `n_clean`, `clean_market_ids`, `created_at_index` and `prev_claim_sha256` | 12.8 |
| R75 | The leaderboard row gains `n_markets_traded`, `n_markets_open`, `explicit_abstain_ppm`, `fill_ratio_ppm`, `turnover_ppm` and `category_coverage_ppm` | 12.10 |
| R76 | New section 12.11 declares `PerMarket`, `AgentResult`, `MarketResult`, `RunProjection`, `RunHandle`, `run_backtest`, `replay`, `EvolutionConfig`, `GenerationResult`, `run_generation`, `evolve`, `resume` and `Archive`: five packages in three later waves were coding blind against undeclared structures | 12.11, 14 |
| R77 | New section 12.12 declares every HTTP route, the `X-Pmx-Token` header and the SSE event names, so U2 and U3 can call U1 blind | 12.12, 13, 14 |
| R78 | `cli_run.py` (E5), `cli_evolve.py` (O2) and `cli_claim.py` (O4) are created with owners and `cli.py` only dispatches: `pmx replay`, `pmx evolve`, `pmx resume` and `pmx claim` had no owning file | 13, PLAN |
| R79 | `web/src/api.ts` and `web/src/types.ts` move to U1, and `web/index.html`, `web/src/main.tsx`, `web/package.json`, `web/tsconfig.json`, `web/vite.config.ts` and the four v1 components go to U3, which deletes the v1 components with its own commit: nine web files had no owner or the wrong one | 13, PLAN |
| R80 | The module map records the relocated schemas, the enumerated lexicon files, the tracked `claims/` and `contamination.json`; U4 must add `[tool.setuptools.package-data]` for `pmx/schemas/*.json` and `pmx/llm/prompts/*.md`, which is a reported contract issue against `pyproject.toml` and not an edit by any package | 13 |
| R81 | Section 14's rows are rewritten against the new names, so every package's deliverable list matches the sections it implements | 14 |
| R82 | Decisions D-13 (the `reconstructed` exemption), D-14 (only fully inside bars are tradable), D-15 (part 2 counts traded markets), D-16 (`K` is computed) and D-17 (schemas inside the package) are added and D-6 is corrected | 14.1 |
| R83 | The two contract fixtures are rebuilt as **complete** journals of small runs rather than excerpts: the backtest one covers the last two bars of the Brexit tape with a two-agent roster (`market_follower`, which places no order, and `contrarian`, which trades), so `seq` is dense, the accounting invariant is asserted per agent, and the old fixture's illegal `hold` that produced a fill and a `+680` PnL for the baseline is gone | fixtures/contract |
| R84 | `tests/test_contract_schemas.py` reads the schemas from `src/pmx/schemas/`, recomputes the fixtures' Brier, `life_mean_price_bp`, accounting and genome hashes from the fixtures themselves, and pins the new rules (no fill on the settling bar, no order for the baseline, hive release after settlement, the projection inputs, the phase order, the `demo-zero` regex, the `wikipedia_asof` revision, the `wiki_subjects` split) | tests |
| R85 | `docs/PLAN_V2_WAVES.md` is corrected where it contradicted the contract: C0's schema paths, E5's `run_backtest(dataset, roster, config, seed)`, the three CLI files, the web ownership split and L1's need for open-market listers | PLAN |

### 15.2 Wave 1 (D1..D7, gate G1)

Fourteen of these rulings (R86 to R99) reconcile the seventy contract issues the seven packages reported;
R100 to R106 are the gate's own, taken while closing the wave and while building the first real dataset.
No ruling here moves a journal byte of an existing run: no run exists, and `ENGINE_VERSION` stays `2.0.0`.

| # | Ruling | Sections |
|---|---|---|
| R86 | A constant has one declaration and the lowest layer that everyone can import owns it: `SEED_SPACE` and `RNG_ALGORITHM_VERSION` are declared in `pmx.rng` and re-exported by `pmx.types`; `JOURNAL_ENCODING` and `JOURNAL_NEWLINE` are declared in `pmx.types` and re-exported by `pmx.journal`, because `pmx.data.schema` and `pmx.data.loader` need them and both sit below the journal in the import order. Section 14's D7 row is read as "exports", not "declares" | 4.2, 6.1, 6.2, 14 |
| R87 | The news order of section 3 gets one arithmetic (`pmx.types.news_rank_key`) and two typed entry points: `rank_news(views)` over the scalar `match_score_permille` of `NewsView`, which is the digest section 3 and 8.3 name, and `rank_news_items(items, *, market_id=None)` over a dataset `NewsItem`, which carries one score per linked market and can only be ranked relative to one. The `RankableNews` protocol is deleted: no `NewsItem` could satisfy it, and D5 had shipped a second implementation beside it. E1 ranks items and then projects the survivors into views | 3, 7.6, 8.3 |
| R88 | `pmx.journal.canonical_sha256(payload)` is the one spelling of "SHA-256 over canonical bytes" for the four hashes of 4.3 that need it (`genome_hash`, `config_hash`, `obs_sha256`, live `forecast_hash`); `pmx.types.market_set_hash` calls it | 4.3 |
| R89 | Section 7.5 has one implementation, `pmx.types.hardness_tags_from_closes`, which `pmx.data.builder.hardness_tags_for` and `pmx.data.migrate_v1` both call. The `upset` window is the last 30 **days** of life and not the last 30 bars, so an hourly dataset does not read it as 30 hours; `illiquid` stays the caller's argument, because it is relative to the dataset's provider slice and no market carries it on its own | 7.5, 7.10 |
| R90 | Section 14's `pmx.journal.events.*` is amended to `pmx.journal.*`. The wave shipped a `sys.modules` alias so both spellings imported at run time, which a type checker cannot follow; there is now exactly one importable spelling, and a test fails if the alias comes back | 9.2, 9.4, 13, 14 |
| R91 | `HttpClient.get_json` and `get_text` accept an absolute URL as `path` and request it verbatim. One provider can need two hosts (Polymarket's Gamma for the metadata, the CLOB for the tape) and the earlier string join produced `https://clob.polymarket.com/https://gamma-api.polymarket.com/markets` and then reported a provider shape change. A second host still deserves a second client, because the throttle is per host | 7.11 |
| R92 | A TLS or certificate verification failure is the one transport failure the client does not retry: the certificate a host serves does not change between two handshakes, and where a regulator has taken the DNS record over (the ANJ wall) three extra handshakes only delay the `ProviderBlockedError` D4's detector must see on the first attempt | 7.11, 13.1 |
| R93 | Every importer signature of 7.12 carries `interval_min: int = 1_440`, and every fetcher signature carries `safety_lag_ms: int = SAFETY_LAG_MS_DEFAULT`. A dataset has one grid (5.3) and one lag, both `BuildConfig` fields, and without the arguments an hourly dataset silently got daily bars and every item silently carried the six-hour default. D6 passes both, and passes them only where a signature declares them | 7.12 |
| R94 | The twelve lexicons plus `stopwords.v1.json` and `paraphrases.v1.json` move to `src/pmx/lexicons/`, for the reason R29 moved the five schemas: `newsbayes` (A1) reads them at run time and a repository-root path does not exist in an installed wheel. `linker.LEXICON_DIR` resolves inside the package | 7.6, 13 |
| R95 | `link_items` **adds** links and does not replace them: a link an item already carries is kept, and where both a stated and a scored link exist for one market the higher score wins. A Manifold comment is the one news item whose link is stated by the venue (at 1000 permille), and the earlier spelling unlinked every comment it was passed | 7.6, 7.12 |
| R96 | Each of the four news modules declares a `BASE_URL` constant, as every importer already did, so `cli_data` reads the host from the module that documents it. The two spellings had already drifted (the Wayback module said `http`, the CLI table said `https`) | 7.3, 7.12 |
| R97 | Section 7.10 item 4 is amended: a migrated demo market carries the hand-written `wiki_subjects` of `migrate_v1.DEMO_WIKI_SUBJECTS`, not `[]`. The old identity contradicted C0's own fixture (`market.demo-brexit-2016.json` carries a real article title) and `test_contract_schemas.py`, which asserts that field is non-empty; and a pack with no subjects is invisible to the linker of 7.6, which compares an item's `wiki_links` against exactly this field. Section 7.10 also now records that `resolved_at_ms = max(day_end(resolved_date) - 1 s, last control point)` and `close_at_ms = resolved_at_ms`, because two v1 markets carry control points after their stated resolution day and identities 2 and 3 cannot both hold otherwise | 7.10 |
| R98 | `counts.illiquid_boundary_milli` is a typed field of `dataset.v1.json` and of `DatasetCounts`: 7.5 requires the `illiquid` tag to be reported with its decile boundary, and a sentence in `notes` is not a report. A provider slice too small for a tenth percentile is absent from the map rather than carrying a sentinel, and the note beside it names those slices. The field is optional in the schema so a manifest written before this ruling still parses | 7.5, 7.8 |
| R99 | `src/pmx/py.typed` exists and `pyproject.toml` carries `[tool.setuptools.package-data] pmx = ["py.typed", "schemas/*.json", "lexicons/*.json", "llm/prompts/*.md"]`, which is ruling R80's line extended by R94's lexicons. Without the marker, `mypy --strict` reports `import-untyped` for every `pmx.*` import from outside `src/` and no test file can be type-checked at all | 13, 13.2 |
| R100 | `BuildConfig.kalshi_series_allow_list: tuple[str, ...] = ()` is a build-time filter, `import_kalshi` narrows both settled listings with it server-side (`series_ticker`, one listing per series), and `_list_rows` stops its descending walk at `window_start_ms - KALSHI_SETTLEMENT_SLACK_MS`. Measured against `api.elections.kalshi.com` on 2026-09-07: `/historical/markets` **ignores** `min_close_ts`/`max_close_ts` (the answer is identical with and without them), and the unnarrowed settled universe runs at about eight thousand rows per minute of close time because of the `KXMVE` shards, so a twelve-month window hit the 200-page cap after 200 000 rows without reaching the window. `series_ticker` is honoured by both endpoints and is the only narrowing that makes a real Kalshi dataset reachable; because the allow-list decides a dataset's universe it belongs in the manifest with the other filters | 7.4, 7.12 |
| R101 | The Manifold creator-resolved filter of 7.4 reads `resolution_source == "creator"` (or the `self_resolved` tag), because `Market` has no `resolverId` field and 7.2 gives it none. Its default stays **on**, as 7.4 states, and the consequence is recorded rather than defaulted away: creator resolution is Manifold's normal mechanism, so a Manifold build must pass `--keep-self-resolved` or the filter removes the whole provider. `pmx data build` now prints a warning naming every requested provider that ended with no market | 7.2, 7.4 |
| R102 | An importer's refusals are counted by the builder, not by the importer: `import_manifold` exposes the pure `classify_lite_market(...) -> str \| None` returning the `EXCLUDE_*` reason, and D6 classifies the payloads it was handed. `manifest.filters.removed` therefore keeps its ten fixed keys and no refusal is invisible | 7.4, 7.12 |
| R103 | The undeclared but necessary extensions of 7.11 and 7.12 are declared: `HttpClient(..., transport=None, clock=time.monotonic_ns, sleeper=sleep_ms)` (the offline seam every importer test needs), `build_user_agent(contact=None)`, `cache_key(method, url, params)`, `sleep_ms(duration_ms)`, `HTTP_TOO_MANY_REQUESTS`, `HttpClient.requests_made` and `HttpClient.proxy`; `fetch_comments(..., index_offset_by_day=None)` (an `mfc` id is positional inside its day and two markets commented on the same day would collide); `wikipedia_asof.asof_days_for(market)` (7.1's weekly schedule has one spelling and one test, and only the market's first `wiki_subject` is snapshotted); `polymarket(..., gamma_client=None)`; `load_dataset(path, *, verify=False)`, `verify_dataset_report(path)` and `reseal_hash(path, manifest)` | 7.11, 7.12, 7.8 |
| R104 | Section 13's module map records the names it omitted and their owners: `PHASE_ORDER`, `CALIBRATION_BINS`, `HORIZON_BUCKETS`, `OpenMarket`, `hardness_tags_from_closes`, `news_rank_key`, `rank_news`, `rank_news_items` and `BuildConfig` in `pmx/types.py` (D1); `validator_for` and `validate_against_schema` in `pmx/data/schema.py` (D1, declared surface of 7.13); `src/pmx/py.typed` (U4). `ResearchGrant` (8.3) carries the two typed fields `news` and `trades` plus a `payload` property rather than one polymorphic field, which is what `mypy --strict` can express | 8.3, 12.11, 13, 13.2, 7.13 |
| R105 | A Polymarket market is forecast-only: the CLOB prices-history tape carries no size and the print tape is ANJ-blocked, so every D4 market has `volume_milli = 0`, `trades = ()` and `quality.n_trades = 0`. R41's exemption from the volume rules of 8.6 covers a `reconstructed` market only, so a Polymarket market cannot fill and cannot pass `min_trades`: the provider is **not** part of a built dataset until a size-carrying tape is reachable, and `pmx data import polymarket` stays as the recorded evidence of the block. The first real dataset is Kalshi and Manifold, which is what PRD AC-1 needs | 7.4, 8.6 |
| R106 | The `wikipedia_asof` snapshot names its market through `match_ids[0]`, and a snapshot whose market did not survive the filters is dropped with the other pruned links. News older than `window_start_ms - opened_early_days` is dropped too and counted, because 7.3 puts no floor under the archive and one item from an older window would sit in `Dataset.news_global` for a whole run. Staging (`data/datasets/<name>/staging/`) and the HTTP cache (`cache/`) live inside the dataset directory and outside the dataset hash, which walks `markets/`, `news/` and `wiki_asof/` only | 7.1, 7.3, 4.3 |

Corrections to the text itself, made in the same pass and not numbered as rulings: section 1.1's time
example said `1_788_739_200_000 is 2026-09-07T00:00:00Z` and was a year out (that instant is
2025-09-07T00:00:00Z; 2026-09-07T00:00:00Z is `1_788_739_200_000`), which is the literal a package copied
into a window and got a twelve-month shift; section 7.2 said Manifold prices "arrive as decimal strings"
when they arrive as JSON numbers, so a money provider's body is read with `get_text` and parsed with
`json.loads(..., parse_float=Decimal)`; and `docs/PLAN_V2_WAVES.md` named `tests/fixtures/kalshi/`,
`manifold/`, `polymarket/` and `news/` where section 13 says `fixtures/<package>/**`.

### 15.3 Wave 2 (E1..E5, gate G2)

The five engine packages reported 69 contract issues (56 after merging duplicates: 12 blockers, 33 majors,
11 minors), the tree diagnostic found 30 cross-package disagreements, and the two reconciliation agents
and the redesign agent left 23 more items for the gate. R200 to R228 settle all of them (R228 was
added by the audit pass of this gate, which found merged issue I09 settled by no ruling while this
sentence claimed otherwise), and R229 records what that pass changed in the measurement itself. **Seven are
resolved against the resolution proposed** and each says why (R202 on regenerating the fixture, R205 on
moving the protocols into `pmx.types`, R207 on one error family, R215 on the reservation, R219 on an
`alpha_ppm` field, R224 on the import path, R225 on where `pmx audit leaks` lives). Four rulings declare a
shape the code does not yet carry and name the package that applies it in the next lot (R213's last-bar
drain, R214's `bar_prev`, R217's continuous calibration, R221's `n_quantile_forecasts` and `seed`); each
one moves `results.json` or the journal of every future run and no run exists. Nothing the two reviews
assign to amendment C1c (decisions D-R1 to D-R14 and D-S1 to D-S14, and the `sensors` keyword the sensor
hook added to `build_observation`) is settled here. **No ruling moves a byte of an existing run:
`ENGINE_VERSION` stays `2.0.0` and `CONTRACT_VERSION` stays `"2.0"` (R227), and 13.2 carries that
trigger in place.**

| # | Ruling | Sections |
|---|---|---|
| R200 | **Gate G2's population is the scripted-stub roster, reached through the real CLI.** The G2 spec asks for a full scripted-stub run and the scripted families are wave 3's, so `tests/stub_roster.py` (E5's test double, created by the gate, never collected by pytest and never imported by `src/`) exposes the two names 10.1 declares for the registry, `DEFAULT_ROSTER` (`contrarian`, `limiter`, `market_follower`) and `make_agent(agent_id, genome)`, and `pmx run backtest` gains `--roster-module` (default `pmx.agents.registry`) so the gate's run and A1's future run use one code path. `pmx.cli_run` read `build_agent`, a name no section declares, and would have exited `NotConfiguredError` on the day A1 lands `make_agent`: the contract was right and the code wrong (I55), so the CLI reads `make_agent` and 10.5 points at 10.1's constructor. `tests/test_runner.py` imports the stubs rather than declaring them a second time | 10.1, 10.5, 13 |
| R201 | **Section 17.9's `pmx.types` row is applied and every placeholder is gone** (I01, I02, I04, I06, I41). Every name of the row is in `pmx.types` with the value the rulings fix (`BINARY_TICK_SIZE_MICRO = 100`, seven `CASH_EVENT_KINDS` with `carry`, `RE_MARKET_ID` over the seventeen providers, `RunConfig.horizons_bars` and `kinds` inside `to_dict()`), and `DECISION_LATENCY_BARS` (16.2, R107), which the row omitted, joins it. `REPUTATION_WINDOW_MARKETS` is a `pmx.types` constant re-exported by `pmx.agents.hive`, like every number a test can pin. `RunConfig.__post_init__` resolves an empty `horizons_bars` to `default_horizons_bars(interval_min)` **before** `to_dict()`, so a config that spells the default and one that omits it share one `config_hash` and one run id, which is what 8.1 and R188 already said and what `run_backtest` alone could not deliver; it moves `run_id` for every config that omits the field, no run exists, and `tests/test_runner.py` pins the fixture's config hash beside today's. The five engine files' local constants, `getattr` shims, `_int_of`/`_tuple_of` re-derivations and structural copies of `pmx.types` records (`AppliedCashEvent`, `EngineCashEvent`, the two id bodies of R176) are deleted; a second spelling of a `pmx.types` name is a defect from this commit on | 8.1, 10.4, 17.9 |
| R202 | **Rulings R129 and R164 are applied, the schema dispatches per type, and the contract fixture is completed rather than regenerated** (I05, I42, I56). `pmx.journal` carries `CashEventApplied`, `InstrumentClosed` and `ForecastResolved` (32 event types, `oneOf` equal to `EVENT_TYPES`, asserted), `decided_at_ms` on `OrderPlaced` and `OrderRejected`, `PHASES = ("execute", "settle")` on `OrderPlaced`, `Filled` and `FeeCharged`, and the eight `market_listed` and two `forecast_recorded` fields are `required`: the runner emits **one** `market_listed` shape for every kind, the eight read off `record.instrument` (R144's view gives exactly R164's binary mapping), and `price_ref_ticks = null`, `horizons = null` on a binary. `validate_event_dict` dispatches on `type` to the `$defs` entry the `oneOf` would have selected (27 ms an event through a 32-branch `oneOf` made a 15 000-event journal take seven minutes to validate) and keeps the whole-schema path for an unknown type. **Against the proposal to regenerate `tests/fixtures/contract/journal.backtest.jsonl` from a run of the fixed runner**: the fixture is a pre-latency journal whose six documented differences from a contract-correct run are what `test_run_reproduces_the_contract_fixture` and `test_the_run_reproduces_the_fixture_payload_for_payload` measure, so a fixture written by the runner would compare a run to itself; the six lines R164 completed were filled in (the eight fields, the two nulls, `decided_at_ms = bar_ms` as a pre-latency journal means) and re-serialised through `canonical_json`, the gate validated all 40 lines against the schema and their canonical bytes, and the two reproduction tests prove the completed lines are byte for byte what the runner emits. 9.2's note reads the post-gate state; `tests/test_rng_journal.py` pins 32 types and `tests/test_contract_schemas.py` asserts the three events **are** in `oneOf` with a class whose `PHASES` matches (`C1B_EVENTS`), the positive form of R164's promise | 9.1, 9.2, 17.9 |
| R203 | **Architecture rule 11 has one body and the plan's F4 row says so** (I07). `pmx.data.sessions` ships `in_session`, `next_bar_ms`, `prev_bar_ms`, `session_bars`, `is_session_close`, `days_since_previous_close`, `load_calendar`, `calendar_from_payload`, `check_calendar` and `generate_calendar`; E1's `Calendar` and E2's `_SessionGrid` call them and keep only the run-window clamping, which is the run's and not the calendar's (`Calendar.next_bar` versus `Calendar.session_next_bar`, R208). The rule-11 test scanned for the identifier `in_session` and let a second implementation ship under the name `covers`; it now also refuses any file outside `data/sessions.py`, `data/schema.py`, `types.py` and `engine/calendar.py` that reads a session's `open_ms` and `close_ms` in one expression. `docs/PLAN_V3_WAVES.md`'s F4 row no longer lists `src/pmx/data/sessions.py` (R174; 17.7 and 13 already said D1). The module has functional tests (`tests/test_types_loader.py`: the generator with a holiday and its overlap refusal, intersection not containment, Friday to Monday, the weekend charged on Monday, `continuous` never a file) | 13, 17.2, 17.7, 17.9, PLAN_V3 |
| R204 | **`applies_at` has one body, in `pmx.engine.calendar`, and its declared name stays `pmx.engine.execution.applies_at`** (I12, the three-bodies mismatch). R175 declared the function in `execution.py` while R183's visibility rule is applied on the observation path, so E1 spelled `cash_event_applies_at`, E2 `applies_at` and a third copy sat in `calendar.py` with no caller, each with its own tuple of the three old-regime kinds; the observation's copy answered `None` for a dividend when the runner passed no calendar while execution's answered `prev_bar`, a leak-boundary rule computed two ways in one bar. The body lives in `calendar.py`, the module both halves of the engine already import (`OLD_REGIME_KINDS`, `BarLookups`, `CashEventStamp`, `InstrumentClock` beside it); `execution.py` re-exports it under R175's name and `observation.py` calls the same object. Its signature is `applies_at(event, instrument, calendar: BarLookups \| None) -> int \| None`, where `BarLookups` is the protocol of 8.3's three lookups (R187) and `None` means there is no calendar to read `prev_bar` from, so a corporate kind is not applied and is therefore never visible, which is the conservative side of the boundary; 17.3's code block and `tests/test_contract_schemas.py`'s pinned phrase read the new signature. Mutation-checked: removing the old-regime shift fails a test in E1's file and one in E2's | 8.3, 17.3 |
| R205 | **The engine's structural protocols have one declaration each, and wave 3 satisfies them by shape** (I47, I48, the four-protocols mismatch). `InstrumentLike` and `CashEventLike` are declared once in `pmx.engine.calendar` (the union of the members execution and the observation builder read; `Market` and `ContinuousInstrument` satisfy both) and imported by `execution.py` and `observation.py`; the read side `MemoryLike` and `HiveLike` are declared once in `pmx.engine.observation` and the runner's write-side protocols **extend** them, so `view` has one declaration; `GenomeLike`, `ReplyLike`, `GatewayLike` and `ResolutionEvent` stay the runner's structural stand-ins until A1, A2, A3 and A5 land the declared classes, which must satisfy them (a gate G3 test imports both and asserts it). **Against I47's proposal** to move `Agent`, `Memory`, `Hive`, `Gateway`, `AgentReply` and `ResolutionEvent` into `pmx.types`: 10.2 to 10.4 and 11.1 declare them in the files of the packages that build them, a `Protocol` matches by shape so the runner needs no import to be annotated, and `pmx.types` is wave 1's closed file; 11.1's argument for `Gateway` and `AgentReply` already places those two in `pmx.types` and nothing more moves. A member the engine only reads is declared **read-only** in any structural protocol (10.1's `Genome` is `frozen=True`, which a mutable protocol attribute would refuse); 10.1 and 10.2 say so | 10.1, 10.2, 13 |
| R206 | **A record's own `kind` is the authority; the R144 view restates it.** `Market.instrument` carries the constant `"binary"`, so a reader that preferred the view answered `binary` for a double whose record said `perp`, while `Calendar.kind_of` and `observation.instrument_kind` read the record: E1 and E2 disagreed about the kind of one instrument inside one run (seven failures). `execution.instrument_spec` reads the kind off the record first and the scale fields off the view, `tests/test_execution.py` pins the tie the real types cannot be in, and 17.1 states the rule in words | 17.1 |
| R207 | **An unknown instrument kind is a `SchemaError` when read off a record or a meta, and an `InvalidConfigError` when a `MarketMeta` is built with one.** `pmx.engine.calendar.meta_kind(meta)` (E1's reader, which `tests/test_observation.py` pins) raises `SchemaError`: the kind came from a file. `MarketMeta.__post_init__` keeps `InvalidConfigError`: a meta is built by `meta_of` from a validated record, and a kind outside the table there is a construction error and not a file's. 13.1's two rows say so; the two conditions are different and the taxonomy is not inconsistent | 13.1 |
| R208 | **The observation path receives the calendar, and the five view caps are `pmx.types` constants** (I08, I10, I11). `Calendar.__init__` gains keyword-only `calendars: Mapping[str, SessionCalendar] \| None = None` (`None` reads `Dataset.calendar(id)` for the ids the run's instruments name, else the synthesised `continuous`); `Calendar.session_next_bar(market_id, t_ms) -> int \| None` is the venue's next bar from the sealed calendar, **unclamped** by the run window, and is the one route to `MarketView.hours_to_next_bar`, because `next_bar` is clamped by `t1_ms` and `last_bar(i)` and would announce both (7.9, R181); `build_observation` gains keyword-only `calendar: Calendar \| None = None` and a run carrying a continuous kind passes it. The runner did not: a continuous run published `tradable = True` on its closing bar, `hours_to_next_bar = 0` across every weekend and no cash event at all, silently, because the continuous path died earlier on `market_listed`. It passes `calendar=self.calendar` now, and `tests/test_runner.py` asserts the exact hours to the next bar of every bar of a session run (`24, 72, 24, 24`) and the Friday funding visible from the Monday; removing the argument fails that test (mutation-checked). `NEWS_VIEW_TEXT_CHARS = 600`, `DESCRIPTION_VIEW_CHARS = 1_000`, `HIVE_RESOLUTIONS_VIEW_MAX = 200`, `MEMORY_NOTES_VIEW_MAX = 20` and `RESEARCH_NEWS_MULTIPLIER = 3`, stated in prose in 8.3 and 8.4 and spelled in `observation.py`, are `pmx.types` constants the builder imports. The `sensors` keyword the sensor hook added to `build_observation` is amendment C1c's to declare and is not settled here | 8.3, 8.4 |
| R209 | **The clock test scans `leak_scan_payload(obs.to_dict())` and bans the structural names of the forbidden records** (I13, I16). 8.3 item 1 banned `resolved_at_ms` anywhere in the key set while 8.3 itself declares `HiveView.resolutions` with that field and R183 puts an applied event's `detail` inside `MarketView.cash_events`: the test as written could not pass on legal data. The exemption is contract: the scan runs over the payload with `HiveView.resolutions` (a settled market's published resolution) and `MarketView.cash_events` (an applied event's verbatim detail) set aside, which is exactly what `assert_no_leak`, the guard the builder runs, scans, and E1's continuous poisoned-future test scans the same payload (the one test-versus-code disagreement of the wave, resolved against the test, which contradicted itself two lines later). 7.9's list is **record-scoped**: no `MatchReason`, `EventCluster`, `Constraint`, `OpportunityEvent` or unapplied `CashEvent` record reaches an observation, and the key scan bans their structural names (`cluster_id`, `constraint_id`, `reasons`, `asof`, `score_permille`, `resolution_span_ms`, `opportunity_id`, `detector_id`, `evidence`, `window`, `duration_bars`, `size_ppm`, `size_net_bp`, `payoff_cents`, `tradable_for_money`, `detail`, and 7.9's fields), while `kind`, `source`, `currency` and `market_ids` are legal keys of legal views and are covered by the poisoned-record test rather than by the key scan | 7.9, 8.3 |
| R210 | **A `wiki_asof` grant carries at most `news_per_market` revisions, most recent first, filtered by `visible_from_ms`** (I14). 8.4 gave the payload no cap while 8.1 makes an observation over `OBSERVATION_MAX_BYTES` raise rather than truncate, so a year of revisions of one subject could kill the bar for every agent. The cap is listed beside the others in 8.1, so E1, D5 and A5 read one number | 8.1, 8.4 |
| R211 | **`prev_bar_forecasts` carries the instrument's previous bar** (I15). 8.3's sentence `bar_ms == now_ms - interval_ms` was not generalised by R192, so on a session instrument the Monday view dropped Friday's legal `live_coop` entries; it reads "the instrument's previous bar (`now_ms - interval_ms` on a `continuous` calendar, ruling R192)", A3's test asserts it per instrument, and R192's list of the places it rewrote gains this one | 8.3, 10.4 |
| R212 | **`LiquidityMarketView` is E2's and reaches no observation** (I17). The E1 brief listed it among 8.3's structures; 8.3 and section 13 are right, `Execution` builds it for a `LiquidityModel` and the observation path constructs and imports none. No text changes; recorded so a later reader does not re-add it | 8.3, 16.1 |
| R213 | **`Execution`'s surface is completed with what the phase order requires, and the last-bar drain is owed and open** (I18, I19, I20, I44, I45). 8.6's listing gains keyword-only `carry_schedules: Mapping[str, CarrySchedule] \| None = None` beside `calendars`, `expire_orders(*, t_ms, markets)` (the open phase's `order_expired`, whose only emitter is execution), `register_agent(agent_id)`, `agent_ids()`, `is_ruined(agent_id)`, `ruined_agent_ids()`, `drain_ruined()` (the `cancelled_order_ids` 9.2 requires and only execution knows) and `mark(..., agent_ids=None)`, exactly as E2 shipped and E5 calls them. `pending_market_ids` is the union, in canonical market order, of the instruments holding an item accepted at their previous bar and the instruments carrying a resting order of any agent (R131 named the first only, while 8.6 has a resting order try against each later bar's range and `execute_bar` is the only entry point that prices one). `FEE_SCHEDULES`, `BORROW_SCHEDULES` and `CARRY_SCHEDULES` are declared registries of `pmx.engine.fees` keyed by `schedule_id`, and `CARRY_SCHEDULES` is empty until F2 lands a dataset that declares a rate-differential row (E2's test builds its own). **Open, stated plainly**: 17.2's "an item whose instrument never has another bar in the run is `order_rejected(not_tradable)` at the run's last bar" is not written, because `Execution` receives neither the resolved window nor E1's `Calendar` and `RunConfig.t1_ms` is legally `None`; on the demo pack 5 of 1 627 queued items are dropped and `tests/test_runner.py::test_every_queued_item_produces_exactly_one_execute_phase_event` pins the drop (`dropped > 0`). The rule stands; `Execution.__init__` gains keyword-only `t0_ms: int` and `t1_ms: int` (the run's resolved window, which `run_backtest` computes), E2 and E5 apply it in the next lot with the test reading `dropped == 0`, and it adds events to every future journal, none of which exists | 8.6, 8.8, 16.2, 17.4 |
| R214 | **Envelope rule 1 binds taker orders, `truncate_for_cash` carries the order, and `quote_bar` carries the previous bar** (I21, I22, I23). A resting buy fills at `min(L, bar.open_bp)`, at or below the ask by construction, so rule 1 as written reported `quote_inside_spread` for obeying 8.6's limit rule: rule 1 reads "a **taker** buy quotes `price_bp >= ask`, a taker sell `price_bp <= bid`; a resting limit fill is governed by 8.6's limit rule and by rule 3", and `check_envelope` checks it on orders whose kind is `market`. `truncate_for_cash` gains keyword-only `order: LiquidityOrder \| None = None` and rule 5's re-established fee takes its side and role from that order (a truncated sell was re-priced as a buy). `quote_bar` gains keyword-only `bar_prev: Bar \| None = None`, the instrument's previous bar from the dataset, `None` only on the instrument's first bar where the floor is `schedule.min_half_spread_ticks`: `HistoricalLiquidity` remembers the last bar it was asked to price, so the half-spread estimate depended on which bars a model happened to be asked about. **Declared now, applied by E2 in the next lot**: it moves the fallback base of every future fill on a quoteless bar (a Kalshi bar without quotes estimates a non-zero `hs` from two non-flat bars), and the gate's AC-3 run was taken on the engine as it stands | 16.1 |
| R215 | **The cash rules are one sentence each** (I24, I25, I26). 8.5's truncation `floor(free_cash / unit_cost)` ignored the fee paid out of the same cash and could leave cash below zero against 8.9: the opening part is truncated to the largest size whose total outlay (opening cost minus closing proceeds plus the fee of 8.8) free cash pays, which is `floor(free_cash / unit_cost)` on a pure opening fill with no fee. A partial limit fill is truncated so that the remainder's reservation stays funded at the maker fee of 8.8, so a remainder never rests against an unfunded reservation and no new `order_expired.reason` is needed (E2's shipped rule; the alternative, a reservation that includes the worst-case maker fee, produces different fill sizes and is not taken). R179's trigger and 8.9's line are one sentence: the cash event that leaves `reserved_cents` above `max(0, cash_cents)` expires every resting order of the agent with `reason = "debit"`, which includes every event that takes cash below zero (a debit that leaves cash positive yet under the reservations broke the invariant line while leaving R179's trigger unfired) | 8.5, 8.6, 8.9, 17.3 |
| R216 | **Venue re-reads belong to the packages that may open a socket** (I27). 8.8 and 17.4 asked E2 to re-read the Kalshi PDF and nine venue pages while architecture rule 5 forbids engine code a socket and the build ran offline. D2 re-reads Kalshi, F1 and F2 the crypto, equity and fx venues, or the gate; until then the shipped numbers, `KALSHI_REDUCED_FEE_SERIES = ()` and `sale_bp = 0` on the three equity rows stand with their `as_of_date`, each row's note recording why, and 8.8's worked values (`175` and `7` cents) pin `taker_permille = 70` | 8.8, 17.4 |
| R217 | **The scoring names are declared where they are read** (I03, I28, I29, I30, I31). Section 14's E3 row reads `log_micronats`, `horizon_buckets` and `horizon_bucket_of` (the field names of 12.1 and 12.11 win over the row's spellings) and `brier_micro` and `neg_ln_micronats` move to the D1 row where 1.2 and 1.3 put them. `logit_milli(prob_ppm) -> int` and `unlogit_ppm(logit_milli) -> int` are declared in 12.1 with the units E3 pinned: a 10 001-entry table indexed by basis points, built in `Decimal` at precision 40, exactly antisymmetric, the index rounding to the nearest basis point with a tie toward even odds, `unlogit_ppm` in `[100, 999_900]` and antisymmetric, monotone and idempotent, the round trip within `LOGIT_ROUND_TRIP_PPM_MAX = 250` ppm. `CalibrationBinView.to_dict()` renders `n_yes_x2` always and every consumer imports the view from `pmx.types` (no module re-exports it). **Declared now, wired by E5 in the next lot**: `project()` builds one calibration entry per resolved continuous horizon through `pmx.metrics.calibration.continuous_entry` keyed `(kind, f"h{horizon_bars}", bin)`, so a continuous row's `ece_ppm` is its own ledger's (17.6) and not `0`; today the projection calls `binary_entry` only and `continuous_entry` has no caller, which moves `results.json` of every future continuous run and no run exists | 8.3, 10.3, 12.1, 12.2, 12.11, 14, 17.6 |
| R218 | **`.scratch/` is git-ignored and scratch files never live in the repository** (I32). An interrupted attempt left three scratch scripts at the root that accounted for 345 of 355 ruff errors and would have been committed; `.gitignore` (C0's) gains the line and section 13's preamble the sentence | 13 |
| R219 | **Section 12.4 is complete** (I33 to I40, the null's statistic). `permutation_null`'s four `...` types are E4's: `forecasts: Mapping[str, Sequence[tuple[int, int]]]` of `(bar_ms, prob_ppm)` in bar order, `market_prices: Mapping[str, Sequence[int]]`, `weights: Mapping[str, Sequence[int]]` (`w_i` in ms, **`bar_weights_ms` of the same bars and nothing else**, or the null measures a statistic the leaderboard does not report; asserted against `scoring.skill_micro` on an irregular grid), `blocks: Sequence[str]`, with `outcomes` and `blocks` aligned to `sorted(forecasts)`, and a continuous call passing empty `market_prices` and `weights`. `iso_week_key(t_ms) -> str` is the one spelling of `f"w{iso_year}-{iso_week:02d}"`, `block_key`'s week branch calls it and `PerMarket.unit_key` is `f"{market_id}/{iso_week_key(cell_ms)}"`. The exchangeability group of R190 is `(block, bar key)`, and on a clustered instrument the block is the cluster, deliberately coarser (a week vector no caller can build is worse than a coarser block every caller can). `Interval.to_dict()` renders `point, lower, upper, sd, n, n_blocks, resamples` and `NullResult.to_dict()` `null_lb_micro, p_value_ppm, permutations`; `opportunity.v1.json` and `model_card.v1.json` carry **mapped** fields, never an embedded `Interval.to_dict()`. The shuffles draw from `stats.permutation` and the inner resamples from `stats.bootstrap`, each from the handed `RngTree`, and the split fixes every published `null_lb_micro`. Deflation is defined at `ALPHA_PPM` only and `bootstrap_lower_bound`'s `alpha_ppm` is for reporting, never deflated (**against I38's preferred half**, an `alpha_ppm` field on `Interval`: every claim interval is built at `ALPHA_PPM` by 12.6, so the field would be a constant column in every `results.json`). `paired_lower_bound` carries keyword-only `alpha_ppm` and `resamples`. E4's test line reads "strictly decreasing in `candidates` on an interval with `sd > 0` and invariant on R68's degenerate interval" | 6.3, 12.4, 16.4, 16.5, 17.6 |
| R220 | **`Journal` exposes its tail** (I43). `Journal.events` copies the whole journal into a tuple on every access, so the runner's contracted "read the fills execution just journaled" (8.7) was quadratic (190 s for a whole-pack limit-order run) and E5 subclassed `Journal` to keep the tail. `Journal.take_tail() -> tuple[JournalEvent, ...]` (the events appended since the previous call, then forgotten) is declared in 9.1, D7's file, and the runner's subclass is deleted | 9.1 |
| R221 | **The leaderboard and projection structures are definable and complete** (I49 to I54, I52). `LeaderboardRow`'s listing puts the six defaulted amendment fields last, keeping every name and default, because a defaulted field never precedes a required one and the class as listed raised `TypeError` at import; the field order in a 12.11 listing is the dataclass's order. `AgentResult` carries `ece_ppm: int = 0` and `sharpness_ppm: int = 0` computed per 12.2 over the agent's own slice, so 12.10's column is read and never recomputed, and `CalibrationBinView` gains no `mean_prob_ppm` (8.3 hands the view to an agent and a per-bin mean probability is a second channel). Nine columns (`sharpe_milli`, `max_drawdown_bp`, `fill_ratio_ppm`, `turnover_ppm`, `abstention_ppm`, `explicit_abstain_ppm`, `category_coverage_ppm`, `ruined`, and `ece_ppm` where no per-slice ledger exists) are 12.3's agent-level number repeated on every slice and 12.10 names them, so a UI never compares two definitions of one column. `leaderboard.build`'s `contaminated` is keyed by `agent_id`; A6 maps its per-model verdict onto the run's seats before handing it over. **Declared now, applied by E5 in the next lot** because each moves `results.json` of every future run: `PerMarket.n_quantile_forecasts: int = 0` (the cell's resolved forecasts whose `quantiles_ticks` was not null; the row's column is its sum, and today every row reports `0`) and `RunProjection.seed: int` (read from `run_started.config`, so `leaderboard.build` builds its `RngTree` from it and `seed_of_run_id`, which parses an identifier's spelling, goes) | 11.5, 12.2, 12.10, 12.11 |
| R222 | **E5's `HiveLike.write_forecast` matches 10.4 field for field** (I46): the four keyword-only arguments of R160 are declared with the contract's defaults and filled per horizon on a continuous instrument, so A3's landing needs no runner edit; A3's test asserts a horizon entry's `visible_from_ms` is `t_h + interval_ms`. No text changes | 10.4 |
| R223 | **Architecture rule 3's allow-list names the declaration site of `Dataset.sealed_market`.** R182 said only `optimizer/folds.py` and `optimizer/claims.py` may spell the name, and a declaration is necessarily a spelling, so the rule-3 test failed on `types.py`; the allow-list reads "where it is declared in `types.py`, and in `optimizer/folds.py` and `optimizer/claims.py`", the test allows exactly that one declaration line and asserts exactly one exists, and 7.2's interface comment says so | 7.2, 17.2 |
| R224 | **A `pmx.types` constant is imported from `pmx.types`; a module that re-exports another module's name does so explicitly** (the import-path and `__all__` mismatches). Five of the six `mypy --strict` errors were a consumer reading a domain constant through an intermediate module with no `__all__` (`RANDOM_WALK_BRIER_MICRO` through `pmx.scoring`, `CONTINUOUS_CALENDAR_ID` through `pmx.engine.calendar`); both metrics files read `RANDOM_WALK_BRIER_MICRO` from `pmx.types`, section 13's owner (**against the tree diagnostic's recommendation** to route both through `pmx.scoring`: `tests/test_stats.py` still cross-checks E3's and E4's spelling, and the owner is the one path a reader need not guess), `pmx.engine.fees` re-exports the price-model constants with `import X as X` because 16.1 lists `MILLI` on liquidity's declared surface, and no module of the package is required to declare `__all__`. Section 13's preamble carries the rule | 13 |
| R225 | **`pmx audit leaks` is A6's `cli_audit.py`, and the four families it runs are named now.** AC-4 requires the poisoned-future, clock, seal and shuffled-outcome tests to pass and to be part of `pmx audit leaks`; the four pass on the tree of 2026-09-09 and the command does not exist, because section 13 gives `cli_audit.py` to A6 (wave 3) and `cli.py` to U4. The families, by test id: poisoned-future `tests/test_observation.py::test_the_poisoned_future_test`, `::test_the_poisoned_future_test_on_a_continuous_instrument` and `::test_one_of_each_cluster_and_detector_record_is_refused`; clock `tests/test_observation.py::test_the_clock_test`; seal `tests/test_builder.py::test_the_built_dataset_loads_seals_verifies_and_fails_on_a_changed_byte` (one byte of a market file changed, `verify` names the file) and `tests/test_types_loader.py::test_seal_stamps_an_imported_dataset_and_rehashes_it`; shuffled-outcome `tests/test_stats.py::test_permutation_null_of_the_market_follower_is_exactly_zero`, `::test_permutation_null_of_a_coin_flip_agent_centres_on_zero`, `::test_permutation_null_of_a_skilled_agent_is_unmatched_and_negative` and the three `test_continuous_null_*` siblings. A6 mounts `pmx audit leaks` as the runner of exactly these ids plus the amnesic test of PRD 6.3 (`--amnesic` and `--no-hive` produce a different journal hash), and it fails when any id is missing from the tree. **What the shuffled-outcome family does not yet prove**: PRD 6.3's population form ("no scripted agent's skill lower bound exceeds zero on the training set over 200 seeds") needs the scripted families of wave 3 and O4's claim path; what exists is the null over synthetic agents and the stub roster. AC-4 is therefore **partial** at this gate and 13's `cli_audit.py` row says what the command runs | 13, 14 |
| R226 | **R151's kind tuple is superseded by R177.** R151's row still spells `CASH_EVENT_KINDS` with six kinds while R177 and 17.3 make it seven (`carry`); the row now says so, and `pmx.types.CASH_EVENT_KINDS` is the seven-tuple | 15.9, 17.3 |
| R227 | **`ENGINE_VERSION` stays `2.0.0` and `CONTRACT_VERSION` stays `"2.0"`.** R201, R202 and R208 change what every future journal carries (the eight `market_listed` fields and two nulls on a binary, the run id of a config that omits `horizons_bars`, the observation bytes of a continuous run) and R213, R214, R217 and R221 will move more when applied; a journal byte moves when an existing journal's bytes change for the same inputs, and no run exists: the contract fixture is a completed historical document and not a run (R202), and the gate's own AC-3 runs are evidence taken on this engine, not artefacts a later engine must reproduce. A bump before the first run would version nothing. The first lot that changes a byte of a journal a run has written bumps both in the same commit, as R111 says | 13.2 |
| R228 | **`Calendar.last_bar` reads `delisted_at_ms` off the instrument record, and `MarketMeta` carries no such field** (I09, left unruled by the first pass of this gate and found by its audit). R186 collapses `delisted_at_ms` and the dataset's window end into one `MarketMeta.resolved_at_ms`, so a meta cannot tell a delisted instrument from one still listed at the window end, while 17.2's `listed(i, t)` and `last_bar(i)` need exactly that difference: the engine reads `Dataset.market(id).instrument.delisted_at_ms`, the one place the value lives unsummed, and `None` there means the instrument is listed to the end of the run. `last_bar(i)` is therefore `min(bar_of(delisted_at_ms) - interval_ms, the run's last grid bar)` when the record carries a delisting and the run's last grid bar otherwise, so the window-end case is clamped by `t1_ms` alone and no `bar_of(resolved_at_ms)` is ever taken for a delisting bar. R186 stands unchanged for what it rules on: the canonical order of section 3, `block_key` and `Folds` read `MarketMeta.resolved_at_ms` and never the record, and the calendar reads the record and never the meta, which is why the two do not compete. Behaviour is unchanged (`calendar.py` already reads the record; its comment cited a ruling of this gate that had not been written, and now cites this one) | 7.2, 17.2 |
| R229 | **AC-3's seed claim is measured with an agent that draws from the `RngTree`, and AC-3 is `partial` until the scripted families land** (the audit pass of this gate). None of R200's three stubs draws from the substream `reset` hands it and neither `execution` nor `liquidity` draws at all, so the 50 seeds of the gate's sweep produced 50 journals differing in the `run_started` line alone (measured: 1 differing line in 94 803, seed 0 against seed 1, run id masked): the sweep measured reproducibility and not the engine under a varying RNG, which is what AC-3's "for 50 seeds" is for. `tests/stub_roster_rng.py` (E5's, created by this gate like `stub_roster.py`, never collected by pytest and never imported by `src/`) is the same roster plus `coin_flipper`, which draws one belief per open market per bar from the substream, so a seed moves the events; `pmx run backtest --roster-module tests.stub_roster_rng` measured 6 seeds of `y2026` on the same protocol (BUILD_STATE 8.3) and `tests/test_runner.py::test_a_seed_consuming_agent_makes_the_seed_change_the_journal_it_reproduces` keeps the claim in the suite, mutation-checked. AC-3 as written asks for the eleven scripted families, so its verdict is **partial** (as AC-4's is for its missing command) and A1's landing of `pmx.agents.registry.DEFAULT_ROSTER` is what regrades it | 10.5, 13 |

Gate G2's measurements (AC-3 on `data/datasets/y2026` through `pmx run backtest --roster-module
tests.stub_roster` and, for the seed, `--roster-module tests.stub_roster_rng` (R229), AC-4 over the four
families of R225, the suite, ruff, mypy and the em-dash sweep) are in `docs/BUILD_STATE.md` section 8,
with their limits, and the audit pass that corrected them is section 8.8.

### 15.4 Wave 3 (A1..A6, gate G3)

None.

### 15.5 Wave 4 (O1..O4, gate G4)

None.

### 15.6 Wave 5 (U1..U4, gate G5)

None.

### 15.7 Wave 6 (L1, gate G6)

None.

### 15.8 Amendment C1 (the wave 2 amendment of `docs/PLAN_V3_WAVES.md`)

C1 writes section 16 before the engine wave starts, so E2 and E5 are built once against the v3 interfaces
instead of twice. R107 to R125 are its first pass and **R126 to R143 are its arbitration pass**, which
answers eighteen findings raised against that first pass. **No ruling here moves a journal byte of an
existing run: no run exists, `ENGINE_VERSION` stays `2.0.0` and `CONTRACT_VERSION` stays `"2.0"`.**

The arbitration pass changed what "C1 does not own" means. R136 and R142 establish that a section of this
document is never a contract issue and that the nine schemas under `src/pmx/schemas/` are C1's, so every
edit R111, R116, R117, R118 and R128 needed in a **document or a schema** is applied in place here, and
section 16.8's table is reduced to code in another package's file. R112 and R119 are unchanged: they name
`pmx.types` and `pmx.agents.protocol`, which C1 does not own, and their gates still apply them.

| # | Ruling | Sections |
|---|---|---|
| R107 | **Decision D-2 is taken the other way and PRD v3 3.3 wins**: an action decided on bar `t` executes at the open of bar `t + interval_ms`. `DECISION_LATENCY_BARS = 1` is a contract constant, never a `RunConfig` field, because a run that could turn the latency off would be a run whose fills the tape never had to honour. The last sentence of 5.4 and decision D-2 of 14.1 are amended in the same pass | 5.3, 5.4, 8.2, 8.6, 14.1, 16.2 |
| R108 | `PHASE_ORDER` is **unchanged** and `execute` stays after `observe`. Draining the queue before the observation is the more physical order and is forbidden: a fill at bar `t`'s open lands in cash and in `avg_cost_bp`, so an observation built after it would carry the price of a bar that has not completed, which is the leak 5.4 exists to prevent. What moves is only what `execute` drains | 8.2, 9.1, 16.2 |
| R109 | `tradable(m, t)` and ruling R9 are untouched; a fourth predicate `actionable(m, t) = tradable(m, t + interval_ms)` is added. An action decided on the last tradable bar has nowhere to fill: it is journaled `order_rejected(not_tradable)` at the execute phase of the next bar and that is the rule, not a defect | 5.3, 8.6, 16.2 |
| R110 | `Execution.place` is called in the `decide` phase and **queues**: it emits no event, moves no cent and reserves nothing. `execute_bar(t_ms=t)` drains what `place` accepted at `t - interval_ms` and emits every execute-phase event, so the accounting invariant of 8.9 and the one-event-per-money-movement rule of 9.3 hold unchanged | 8.2, 8.6, 8.9, 16.2 |
| R111 | Four edits to `journal.v2.json` (C0's file) **and to the matching rows of section 9.2's catalogue** are reported as a contract issue and applied by gate G2 in the commit that lands E2 and E5: `filled.price_source` gains `open`, `impact` and `mm`; `filled.unfilled_reason` and `order_rejected.reason` gain `no_liquidity`; `order_placed` and `order_rejected` gain a required `decided_at_ms`. **Superseded in part by ruling R129**, which applies the catalogue rows and the schema here: 9.2 and `journal.v2.json` are files C1 owns, so the premise of the deferral was false and the contract was left contradicting itself. What survives of this ruling is the `decided_at_ms` `required` list and the `pmx.journal` dataclasses, which are D7's. The fourth is not cosmetic: under deferral `item_index` indexes the **previous** bar's `action_received`, and without `decided_at_ms` a rejection cannot be traced to the intent that caused it. If a journal exists when G2 lands them, `ENGINE_VERSION` and `CONTRACT_VERSION` bump in the same commit | 9.2, 16.1, 16.2, 16.8 |
| R112 | `RunConfig` gains `liquidity: str = "historical"` and `liquidity_params_hash: str = ""` (section 8.1's listing is amended here; `pmx.types` is D1's file and gate G2 applies the two lines). Both enter `to_dict()`, therefore `config_hash`, therefore the run id, for ruling R8's reason: two runs that differ only in the liquidity they faced must not share a directory, a journal or a claim | 8.1, 2, 16.1, 16.8 |
| R113 | A fill price is computed in exactly one module, `pmx.engine.liquidity` (E2's file). Steps 1 to 4 of 8.6 become the normative definition of its `historical` implementation, whose fallback base moves from `bar.vwap_bp` to `bar.open_bp` because an order queued at `t - interval_ms` executes at the open of `t`; `price_source` reads `open` where it read `vwap`. R41's exemption of a `reconstructed` market from the volume rules is restated verbatim inside the envelope rule, so no implementation can drop it by accident | 8.6, 13, 16.1 |
| R114 | A model never receives a `Market` and never receives an agent id. `quote` takes a `LiquidityMarketView` that carries no `resolution`, no `resolved_at_ms` and no `final_price_bp` (7.9 would otherwise be reachable through the execution path), and no identity, so a price cannot depend on who is buying. The allocation half of "same tape for everyone" was still decided by `agent_id` order when this ruling was written, and ruling R141 makes it true rather than weakening the claim | 7.9, 16.1 |
| R115 | The three bounds of the envelope cannot contradict each other: the observed bid and ask are **clamped into `[bar.low_bp, bar.high_bp]` first**, and the no-quoting-inside rule is applied to the clamped value. Without the order a bar whose quotes sit outside its traded range would make every implementation fail the envelope check through no fault of its own | 16.1 |
| R116 | Cluster membership is partly a function of `resolved_at_ms` and of a human review, both forbidden by 7.9, so `EventCluster` and `Constraint` carry `asof: bool` and every `MatchReason` carries its own. Only an **as-of** cluster's price arithmetic may reach a feature vector; no `cluster_id`, no reason, no score, no manual override and no detector output ever reaches an observation, a prompt or a research result. The positive half is equally normative: a cluster peer's price is visible exactly as any other market's is, and the engine never adds a market to an observation because it is a peer, which would leak the grouping through the market set | 7.9, 8.3, 16.3, 16.5 |
| R117 | `clusters/` is sealed with the dataset: the walk of 4.3 gains that directory, `seal_dataset` and `verify_dataset` cover it, and the manifest gains the `clusters` block of 16.3. Sections 4.3, 7.1 and 7.8 and `dataset.v1.json` are amended here (rulings R136 and R142); `pmx.data.loader` is D1's and is applied by gate G7. A dataset with no `clusters/` directory hashes exactly as it does today, because the walk of an absent directory adds no line, so no hash that exists on 2026-09-08 moves | 4.3, 7.1, 7.8, 16.3, 16.8 |
| R118 | `block_key` gains a keyword-only `cluster_id: str | None = None` (12.4, E4's signature, shipped in wave 2 and filled by R1b in wave 7). Two venues' markets on one event are not independent draws, and the plan already said the block bootstrap resamples "by event cluster" while no `EventCluster` existed; the keyword-only default is the extension mechanism of preamble rule 2, so nothing is widened later | 12.4, 16.3, 16.8 |
| R119 | `Genome` gains a fifth component `card: ModelCard | None`, always rendered by `to_dict()` and `null` for every family but `torch_policy`, for the reason `prompt` exists: the weights hash must sit **inside** `genome_hash` or a claim names a model it cannot pin. A1 ships the field in wave 3, when no genome hash exists yet and it is free; adding it in wave 9 would move every genome hash ever computed. The run manifest of 9.5 gains `features_version`, `features_hash` and `model_cards` when the roster carries a `torch_policy` (applied by gate G9) | 10.1, 9.5, 16.5, 16.8 |
| R120 | Preamble rule 3's list of legal float sites gains a **fifth**: the inference boundary of `pmx.agents.families.torch_policy`, where a model output crosses into `pmx.features.quantise` and dies as a ppm integer. Section 6.4 gains the matching honesty: a `torch_policy` run **replays** byte-identically from its journal on any machine, and **reruns** byte-identically only when its card declares `inference_kind == "integer_table"`. AC-16 asks for the replay, and the replay is what the journal guarantees | preamble, 6.4, 16.5 |
| R121 | The v3 identifier regexes are declared in 16.7 and their constants live beside their owning module (`pmx.data.clusters.RE_CLUSTER_ID` and `RE_CONSTRAINT_ID`, `pmx.analysis.report.RE_OPPORTUNITY_ID`, `pmx.learn.cards.RE_MODEL_ID`), not in `pmx.types`: D1's file shipped in wave 1 and every later wave would have to edit it. Section 2 stays the v2 table and 16.7 is its continuation | 2, 16.7 |
| R122 | Each new package's `__init__.py` is owned by the **amendment that opens its wave** (C2 `analysis/`, C3 `features/` and `learn/`, C4 `adversary/` and `adversary/train/`, C5 `portfolio/`), as C0 owned the v2 ones. Five packages of one wave land in the same directory and none of them may create another's file, so without this the first to run would breach section 13 or the wave would deadlock | 13, 16.6 |
| R123 | `src/pmx/engine/liquidity.py` has one owner, **E2**; R1c adds `calibrated_impact` to it in wave 7 by the agreement recorded in the module map, exactly as R1a adds the `stats` subcommand to D6's `cli_data.py` and R1d the hourly option to D6's `builder.py`. `src/pmx/cli_portfolio.py`, which PRD v3 section 10 names and `PLAN_V3_WAVES.md` omits, belongs to R5a. Every other new file of 16.6 has exactly one owner and no file has two | 13, 16.6 |
| R124 | `tests/test_architecture.py` gains rules 7, 8 and 9 (no torch, sklearn or sentence_transformers outside `learn/` and `adversary/train/`; nothing in `analysis/` writes a journal or reads the sealed fold; `engine/liquidity.py` is the only place a fill price is computed). All three pass on the tree of 2026-09-08, where none of those directories exists: a rule that binds only when its subject appears is still a rule, and it binds on the first commit that adds one | 16.6 |
| R125 | `analysis/` and `models/` are generated and git-ignored (a contract issue against `.gitignore`, C0's file, applied by gate G8). Nothing under `analysis/` is replayable evidence, because nothing there writes a journal; a claim that cites a detector cites its `params_sha256` and its `dataset_hash`, never a file path | 13, 16.4, 16.8 |
| R126 | **`quote` becomes `quote_bar` and takes a `LiquidityOrder` batch.** The old signature `quote(market_view, bar, side, size_milli, now_ms)` carried neither the order kind, nor the limit price, nor the fee schedule, while the same subsection made the model responsible for all three: 8.6's limit rule (`min(L, bar.open_bp)`, `no_cross`) is unimplementable without `L`, and envelope rule 5's `role` is unknowable without `kind`. A frozen `LiquidityOrder(side, kind, size_milli, limit_price_bp, resting_since_ms)` and a keyword-only `schedule: FeeSchedule` fix that. The call is a **batch** per (market, bar), not a loop: under the latency rule every order in it was queued a bar earlier and arrives at the same open, so a per-order call would invent an arrival sequence the tape never had, and rationing a scarce cap fairly needs the whole batch. `check_envelope` takes the same `Sequence[LiquidityOrder]`, so the limit path is exercised by the function every implementation must pass | 8.6, 16.1 |
| R127 | **The per-bar volume cap is rationed pro rata, and envelope rule 4 is restated as multiset invariance.** Rule 4 demanded that the aggregate `filled_milli` and the aggregate notional be permutation-invariant, while 8.6 step 2 consumed a shared cap first come first served and step 4 priced each fill from its own size: two buys of 80 and 40 against a cap of 100 give `100 * base + 6_800` in one sequence and `100 * base + 5_200` in the other, so E2's mandatory property test contradicted E2's mandatory implementation. The finding's own remedy, averaging a linear impact curve over the consumed interval, is **not** taken: with an integer price per fill that is invariant only up to rounding, so it trades an exact contradiction for an inexact one. Pro-rata rationing removes the cause instead: the allocation is a function of the batch as a set, the multiset of fills is exactly invariant, and the arithmetic stays integral. `allocate_cap` is the one implementation and the remainder rule is stated in 8.6 step 2 | 8.6, 16.1 |
| R128 | **No file inside `clusters/` carries a `dataset_hash`.** R117 puts both cluster files inside the walk of 4.3, and `cluster.v1.json` made `dataset_hash` a required property of `clusters.json`: a file whose bytes are an input to the hash cannot also hold it, so R1b and gate G7 faced a fixed point nothing could satisfy. The field is removed from the schema and from the fixture; `dataset_name`, `overrides_sha256`, the manifest's `clusters` block and the walk itself are what tie the document to its dataset, exactly as `manifest.json` is excluded from the walk for the same reason | 4.3, 16.3, `cluster.v1.json` |
| R129 | **R111's journal edits are applied now, not deferred.** R111 justified the deferral by saying the catalogue rows lived in a file C1 does not own; 9.2 is in this document and `journal.v2.json` is in `src/pmx/schemas/`, so the premise was false and the contract was left contradicting itself (8.6 mandated `price_source = "open"`; 9.2 forbade it). Both are amended here: `filled.price_source` and `filled.unfilled_reason` gain their values, `order_placed` and `order_rejected` gain `decided_at_ms`, and `order_rejected.reason` needs no widening because it was never an enum. `decided_at_ms` is **declared but not yet `required`** in the schema: `pmx.journal`'s dataclasses (D7) cannot carry it and the shipped backtest fixture is a pre-latency journal, so promoting it is one commit with one owner (section 16.8) rather than a schema that rejects the events the contract orders E2 and E5 to write | 9.2, 16.1, 16.2, 16.8 |
| R130 | **`Fill` carries `base_price_bp`, `slippage_bp` and `role`, and the cash truncation is `truncate_for_cash`.** The `filled` event requires the first two and 8.6 keeps them normative, yet neither was on `Fill` and neither could be recomputed by `Execution` without breaching architecture rule 9. Worse, 8.6 step 5 shrinks a fill against cash **after** the model returns, which moved `unfilled_reason` to `cash` and made the model's `fee_cents` wrong while envelope rule 5 asserted the fee as an invariant. `truncate_for_cash(fill, *, max_filled_milli, schedule)` lives in `pmx.engine.liquidity`, recomputes `filled_milli`, `fee_cents` and `unfilled_reason` under 8.6's precedence, and rule 5 is now stated over the fill the journal writes | 8.6, 16.1 |
| R131 | **`Execution.pending_market_ids(t_ms=...)` is declared and the runner drives the drain over it.** 16.2 promises `order_rejected(not_tradable)` for the market that settled, but the only enumeration the runner had was E1's `BarSlice`, and a market that settled at `t - interval_ms` is in none of its four tuples at `t`, while the queue is never journaled and had no accessor. The rejection could therefore never be written. The read side of the queue is now part of the contract, in canonical market order, and the runner resolves each `Market` from the dataset; E5 asserts that every accepted item produces exactly one execute-phase event | 8.6, 16.2 |
| R132 | **An as-of cluster is matched by content only; `resolution_tolerance_ms` is off that path.** The visibility rule turned on a stored reason, while `resolution_tolerance_ms` was declared as a filter over every candidate pair: a pair kept or dropped by a tolerance on resolution dates is a pair selected with hindsight whether or not a reason recorded it, so hindsight-filtered groupings could reach a trained policy through `cluster_gap_bp` and `cluster_peer_count`. The matcher now stores a `resolution_date` reason whenever the tolerance decided anything, and an `asof: true` cluster carries `resolution_span_ms = -1`, which `cluster.v1.json` enforces, so the record shows on its face that no resolution date was read | 16.3, 16.5, `cluster.v1.json` |
| R133 | **A cluster or constraint feature is computed over the peers listed at `now_ms`.** 16.5's ban list was bar-level; membership was not addressed, so a static whole-window `EventCluster` let `cluster_peer_count` at bar `t` count a peer created after `t`. "A second venue will list this event" is future information and it correlates with the events that matter. `cluster_peer_count` counts only members satisfying `listed(peer, now_ms)`, `cluster_gap_bp` is clamped to its `lo` when fewer than two qualify, and E1's poisoned-future test gains a peer created after `now_ms` | 16.5 |
| R134 | **`adversarial_mm` never reads the hive.** Its row promised prices as a function of "the population's revealed behaviour (the hive's reputations)", which the protocol cannot supply and R114 forbids: reputations are per `(agent_id, category)` and are built from settled markets, so they would carry both an identity and post-resolution information into the price path. Its inputs are its genome, the `LiquidityMarketView`, the current `Bar` and its own `ObservedFlow` history, which is aggregate revealed behaviour with no identity on it. If more population state is wanted later it joins `ObservedFlow` as an anonymous per-bar aggregate | 16.1 |
| R135 | **The impact calibration and the liquidity decile are fit on the training fold.** Both were whole-dataset projections while every neighbouring rule is strict about exactly this: `model_card.v1.json` pins `train.fold` to `"train"` and 8.1 raises `LeakError` on a memory snapshot from a later run. A claim on the sealed fold priced by coefficients regressed on the sealed fold is contaminated in its PnL half even though the agent saw no forbidden field. The manifest's `impact` block carries `fit_fold: "train"`, `fit_t1_ms`, `params_sha256`, `impact_bp_per_pct_by_decile` and `n_markets_fit`; `liquidity_decile` ranks on the same fold; `pmx claim` refuses a `calibrated_impact` run whose `fit_t1_ms` exceeds the claim's `t0_ms` | 16.1, 12.8, `dataset.v1.json` |
| R136 | **A section of this document is never a contract issue.** C1 amended 5.3, 5.4, 8.2, 8.6 and 12.11 in place but pushed four other normative passages onto later gates, leaving the contract contradicting itself where packages read it: 8.1's `RunConfig` had neither liquidity field while 12.11's `RunProjection` exposed both; 7.9's leak list stopped short of the cluster-derived names that 16.3 says in the present tense it contains; 12.4 still declared `block_key(market)` while section 14's E4 row already read the widened form; and the preamble still counted four float sites with no `torch_policy` row in 6.4. All four are applied here. E1, E4 and D1 read the stale text, not the ruling | preamble, 4.3, 6.4, 7.9, 8.1, 12.4, 16.8 |
| R137 | **`tests/e2e/test_e2e_0_base.py` belongs to gate G6.** PRD v3 section 2 lists rung 0 with an end-to-end test and section 9 makes the suite cumulative, but `tests/e2e/` was assigned to G7..G11, which close rungs 1 to 6: nothing owned rung 0's file, so G7's mandate to run `tests/e2e/` in full would either run a file nobody wrote or pass on a missing rung. G6 is the last gate of part 1 and the first point at which build, run, replay and claim all exist. A rung's gate fails when a delivered rung's file is absent, so an empty directory is not a pass | 13, 14, 16.6 |
| R138 | **`vwap` is not a value a `LiquidityModel` may return.** R113 abolished the vwap base and no implementation row lists it, yet `Fill.price_source` still permitted it, so a model could have journaled a source the amendment removed on purpose. It is struck from `Fill` and from 9.2's row. It stays in `journal.v2.json`'s enum, and only there, so that a journal written before the amendment still validates | 9.2, 16.1 |
| R139 | **`run_backtest`'s `liquidity` is required and keyword-only, like `tree`.** The paragraph said in one sentence both that the runner never builds a model and that `None` means "build the one `config.liquidity` names". A default that contradicts its own paragraph is a defect, not a convenience. Every caller builds its own with `make_liquidity(config)`; E5's `pmx.cli_run`, O2's `run_generation` and O4's `claim` are those callers | 12.11, 14, 16.1 |
| R140 | **`float_view` may be called at the `torch_policy` inference boundary.** 16.5 confined it to `learn/` and `adversary/train/` while putting the inference boundary in `agents/families/torch_policy.py` and requiring a `cpu_float32` card to run a float32 forward pass there: R3e was told to do something the same subsection forbade. The confinement is restated as what it protects, which is that nothing returns through it, and architecture rule 7's wording is aligned so the test matches the prose | 16.5, 16.6 |
| R141 | **R114's fairness claim is made true rather than weakened.** `quote` being identity-free made the price schedule fair while the cap was still allocated in canonical order, so on every thin bar the agent whose `agent_id` sorts first filled and the last one did not, systematically, for a whole run; under evolution, where the optimizer assigns `agent_id`, a naming accident became a fitness edge. Pro-rata rationing (R127) makes the allocation identity-free too, so "same tape for everyone" holds in outcome and not only in the signature. The residual is one milli-contract of remainder, which `Execution` truncates away | 16.1 |
| R142 | **Section 13's rows name C1 where C1 is the owner.** The amendment's own inputs had two owners: 16.8 claimed `docs/CONTRACTS_V2.md`, the schemas, both test files and the contract fixtures, while section 13 still said C0 for all of them and "input, never edited by a package" for `docs/PLAN_V2_WAVES.md`, which C1 had in fact edited. Four rows are amended: the contract and the plan are amended by the part-2 amendment package of each wave (C1..C5), and the two test files and the contract fixtures are C0's, extended by C1..C5 | 13, 16.8 |
| R143 | **A constraint that names a cluster lives inside it.** `Constraint.cluster_id` was typed and left unexplained, and C1's own fixture filed a two-market `complement` against a cluster holding only one of the two. R2b and R2c would then disagree about which markets a `divergence` or a `logic` event may cite, while 16.4's `opportunity_id` hashes `cluster_id` and `constraint_id` together as if they were consistent. When `cluster_id` is not `None`, every id of the constraint's `market_ids` is in that cluster's `market_ids`, and the matcher extends the cluster rather than filing against a partial one. The fixture is corrected by extending the cluster, which is what the rule tells the matcher to do | 16.3, 16.4, `cluster.v1.json` |

---

### 15.9 Amendment C1b (the instrument generalisation of `docs/PRD_V4_MULTI_ASSET.md`)

C1b writes section 17 before the engine wave starts, so that E2, E3 and E5 are built once against
sections 16 and 17 together. R144 to R166 are the instrument model; R167 to R170 record the four data
decisions gate G1 carried into G2 (`docs/BUILD_STATE.md` sections 5.2 to 5.5), which the data package is
implementing in its own files at the time of writing and which the contract must state in the same words;
R171 and R172 are the ownership and the architecture rules. **R173 to R199 are the arbitration pass**, which
answers twenty-seven findings raised against the first pass (two blockers, sixteen majors, nine minors);
three findings were resolved against the fix they proposed, and each says why (R173 on the binary slippage
identity, R180 on the fixture, R190 on permuting skill values). **No ruling here moves a journal byte of an
existing run: no run exists, `ENGINE_VERSION` stays `2.0.0` and `CONTRACT_VERSION` stays `"2.0"`.** Every
normative passage the amendment changes lives in a file C1b owns and is amended in place (ruling R136
applies to this amendment as it did to C1); what is left is code or a schema in another package's file,
listed in section 17.9 with the gate that applies it.

| # | Ruling | Sections |
|---|---|---|
| R144 | **The six kinds are one closed enumeration and `Market` is the binary instrument.** `INSTRUMENT_KINDS = ("binary", "spot_crypto", "perp", "fx", "equity", "future")` in `pmx.types`; `Instrument` is the common base (`provider`, `vendor`, `symbol`, `kind`, `currency`, `tick_size_micro`, `point_value_micro`, `session_calendar_id`, `fee_schedule_id`, `borrow_schedule_id`, `carry_schedule_id`, `listed_at_ms`, `delisted_at_ms`, `short_allowed`, `interval_min`); `Market` keeps its name and every v2 field in code, schema and disk and satisfies the base through the view `Market.instrument`, so nothing moves out of it; a continuous instrument is a `ContinuousInstrument` under `instrument.v1.json`, which refuses `kind == "binary"` because there is one file shape per record. The id field stays `market_id` in every event, view and signature for every kind: it is the id namespace, not a claim about the kind. `MarketMeta.kind`, `Dataset.calendar`, `BuildConfig.kinds` and `RunConfig.kinds` are declared | 1.1, 7.2, 7.4, 8.1, 17.1 |
| R145 | **A binary is `tick_size_micro = 100`, `point_value_micro = 1_000_000`, not the PRD's `10_000`.** Ten thousand millionths of a quote unit is one cent, so PRD v4 1.2's row would price 6 327 ticks at 63.27 USD and forty contracts at 2 530.80 USD against section 1.4's 25.31 USD; one basis point of a one-unit payout is 100 micro. With `100` the identity `cost_cents(size, p) == cash_out_cents(size * MILLI, p, 100, 1_000_000)` holds for every legal `size` and `p` (E2 asserts it over the full range), `price_ticks == price_bp`, and no bp price already written changes value, which is the property the PRD's sentence was written to secure. The PRD's BTCUSDT, ES and EURUSD rows are right and are kept verbatim; the PRD defers the formulas to this amendment, and its binary row is corrected by the contract issue of ruling R189 | 1.1, 17.1 |
| R146 | **One rounding, at the end, against the agent.** `cash_out_cents` rounds up and `cash_in_cents` rounds down, exactly as `cost_cents` and `proceeds_cents` do; a mark is `floor` for a long and `-ceil` for a short. PRD v4 1.2's "round half up, once, at the end" is read as "once, at the end": a half-up on a cash movement would round for the agent half of the time, create cents by rounding and break `proceeds <= cost`, which section 1.2 forbids and the worked examples pin. `round_half_up` is for a score, a quantile and a split ratio, never for a cash movement. No intermediate is rounded: the four-factor product is exact and divided once | 1.2, 17.1 |
| R147 | **Overflow is bounded on what is stored, not on what is computed.** Every journaled, manifested or indexed integer fits `INT63_MAX`; the four-factor `notional_micro` reaches `10**45` at the caps, is computed in Python's exact integers and is never written. The caps that make the stored side hold are `PRICE_TICKS_MAX = 10**12`, `SIZE_MILLI_MAX = 10**12`, `TICK_SIZE_MICRO_MAX = 10**9`, `POINT_VALUE_MICRO_MAX = 10**12` and the per-fill check `notional_micro <= NOTIONAL_CENTS_MAX * NOTIONAL_DENOMINATOR` (`NOTIONAL_CENTS_MAX = 10**15`), which `Execution` applies before pricing and refuses as `order_rejected(bad_size)`. A port to fixed-width arithmetic must widen and never reorder the division | 8.4, 8.6, 17.1 |
| R148 | **`size_milli` and `price_ticks` are the two units, and the v2 field names carry them.** A continuous instrument's `size`, `target_position` and `position` fields are milli-units and its `_bp` price fields are ticks, so `filled`, `market_priced`, `order_placed`, `MarketAction` and `PositionView` stay one event and one shape per name; a binary keeps whole contracts and bp everywhere it has them, becomes `size * MILLI` at the liquidity boundary as 16.1 already does, and is truncated to whole contracts there as before. `actions.v2.json` and `journal.v2.json` widen the bounds to `SIZE_MILLI_MAX` and `PRICE_TICKS_MAX`; the loader and the runner enforce `1..9_999` and whole contracts on a binary, where the schema used to. `MILLI` is declared in `pmx.types` and re-exported by `pmx.engine.liquidity` (R86's rule) | 1.1, 8.4, 8.5, 9.2, 17.1, `actions.v2.json`, `journal.v2.json` |
| R149 | **A bar exists only inside a session, and the run calendar is the union of the instruments' bars.** A session calendar is a **dated** record (`session_calendar.v1.json`: explicit `sessions [{open_ms, close_ms}]` for the window, because daylight saving makes a weekly UTC template wrong for half the year), generated by F4, sealed with the dataset at `calendars/<id>.json` inside the walk of 4.3 with `instruments/`. A bar exists iff its interval intersects a session; a bar outside every session, or a missing bar inside one, fails the loader. `Calendar.bars()` yields every grid point at which at least one instrument has a bar and nothing else; a `continuous` calendar reduces every rule to 7.2's dense grid, so no binary file and no hash of 2026-09-08 moves | 4.3, 5.2, 5.3, 7.1, 7.8, 17.2 |
| R150 | **A continuous instrument is tradable while it is open and before its last bar, and its last bar is a fill, not a mark.** `open(i, t) = listed and in_session`, `tradable(i, t) = open and t < last_bar(i)`, `settles` never holds and `closes(i, t) = (t == last_bar(i))`; `actionable` reads `t + interval_ms` as the instrument's next bar. At `last_bar(i)` (`delisted_at_ms` or the window end, a fold's edge included) `Execution.force_flat` closes every position at the bar's close through an event fill that pays the taker fee, and the runner emits `instrument_closed`. A run therefore never ends with a paper number nobody could have realised, and a claim on the sealed fold cannot carry a position across its edge. 8.7's "positions ride to settlement" is the binary row of this rule | 5.3, 8.2, 8.6, 8.7, 9.2, 17.2, 17.3 |
| R151 | **Every cash flow that is not a fill is a dated `CashEvent`, applied by execution in the settle phase and journaled once.** `CASH_EVENT_KINDS = ("funding", "dividend", "split", "roll", "borrow_fee", "forced_flat")` (superseded by R177 on the kind tuple: `carry` is the seventh, ruling R226); the first four come from data (`origin = "data"`), the last two are the engine's. `Execution.apply_cash_events` applies the events with `bar_of(t_ms) == t` in `(t_ms, kind order, cash_event_id)` order, agents in agent order, after the binary settlements; one `cash_event_applied` per (agent, instrument, event) with a non-zero position before or after. One event per money movement is kept: a cent moves in exactly one of `filled`, `fee_charged`, `settlement_applied` or `cash_event_applied`, and a `roll` or a `forced_flat` carries `0` there because its money moves in its event fills. A `CashEvent` record never reaches an observation, a prompt or a research result (a dated future event is future information; hiding an announced dividend is the price of one rule), and 7.9's list is extended by its fields; a venue's fixed schedule is not on the list | 7.9, 8.2, 8.6, 8.9, 9.2, 9.3, 17.3 |
| R152 | **A roll is two event fills at the two contracts' prices, priced by `pmx.engine.liquidity.event_fill`.** A position held across a roll is closed at `from_price_ticks` and reopened at `to_price_ticks`, each leg a `filled` with its taker `fee_charged` and an `order_placed(origin="roll")`, the gap recorded in `detail.gap_ticks` and never traded through. The forced flat is the same mechanism with one leg at the bar's close. `event_fill` lives in E2's `liquidity.py` so architecture rule 9 holds, emits `price_source = "event"`, which no `LiquidityModel` may return, and is not driven by `check_envelope` because it is not a model: its price is a printed price of the tape. These are the only `order_placed`, `filled` and `fee_charged` events written in the `settle` phase; `journal.v2.json` and the classes' `PHASES` admit it together at gate G2 (R164) | 8.6, 9.2, 16.1, 17.3, `journal.v2.json` |
| R153 | **A split multiplies the position half-up away from zero and divides the average cost.** `position_after = sign(q) * round_half_up(abs(q) * numerator, denominator)`, `avg_cost_ticks_after = round_half_up(avg_cost_ticks * denominator, numerator)`, `cash_delta_cents = 0` (cash in lieu is not modelled; the rounding is at most half a milli-unit and is stated so nobody "fixes" it), every resting order on the instrument is expired with `reason = "corporate_action"` because its price is in the old scale, and a split on the same bar as a dividend applies after it. Equities are stored raw; the adjusted view for features multiplies earlier prices by `denominator / numerator` and never touches execution | 9.2, 17.3 |
| R154 | **A short on a continuous instrument is a liability, guarded by free cash, and never by an invented margin account.** Opening a short receives `cash_in_cents`, covering pays `cash_out_cents`, the position is marked `-ceil` of its notional, `positions_value_cents` and therefore `equity_marked.positions_value_cents` are signed, and equity may fall below zero while a fill never takes cash below zero (a debit cash event may, ruling R179). The opening notional of a short may not exceed the agent's free cash at the fill, so a cover up to a doubling is always affordable; beyond that the cover is truncated by `truncate_for_cash`, the residual is carried, the forced flat reports it as `position_after != 0` and 8.7's ruin freezes the agent. `short_allowed` is per instrument from the kind table (`spot_crypto` never, `equity` only with a borrow schedule) and the loader refuses a value the table forbids. A binary's NO leg keeps 8.5 exactly | 8.5, 8.7, 8.9, 9.2, 17.3 |
| R155 | **Fee, borrow and carry schedules are data with a source URL and a date, and `FeeSchedule` gains `kind` and `model`.** `FEE_MODELS = ("pq_permille", "notional_bp", "per_contract", "zero")`; `pq_permille` is 8.8's binary rule to the letter, the other three are 17.4's bodies, reached through keyword-only defaults on `fee_cents` (preamble rule 2) so the five binary schedules and every 8.8 worked value are unchanged. Every fee rounds up once and envelope rule 5 holds over the fill the journal writes. `CarrySchedule` (`role: "borrow" | "carry"`, `rate_ppm_per_day`) is the same record family; one borrow schedule ships, no carry schedule does, and an `fx` instrument's swap is off by default | 8.8, 17.4 |
| R156 | **When no quote is known the envelope's rule 1 is the Corwin and Schultz half-spread, floored by the schedule.** `half_spread_ticks(bar_prev, bar, schedule=schedule)` computes the estimator on two consecutive bars' highs and lows in `Decimal` at precision 40 (the one legal non-integer arithmetic of section 1.3, correctly rounded and therefore platform-identical), rounds half up to ticks, clamps a negative or undefined estimate to `0` and applies `schedule.min_half_spread_ticks`; a buy's base is `open + hs` and a sell's `open - hs`, both inside rule 3's range. On every binary schedule the floor is `0` and two identical flat bars estimate `0`, so 8.6 step 3's fallback to the open is unchanged on the demo pack. The worked value `14_619` ticks is pinned by the schema test | 16.1, 17.4 |
| R157 | **A continuous forecast is per declared horizon, and `prob_ppm` is the shortest horizon's up-probability.** `RunConfig.horizons_bars` (empty meaning `default_horizons_bars(interval_min)`: one bar, one day, one week, in bars of the instrument's own sequence, duplicates removed) names the horizons; `Actions.horizon_forecasts` carries one `HorizonForecast(market_id, horizon_bars, up_probability_ppm, quantiles_ticks)` per pair, with `duplicate`, `bad_horizon` and `bad_quantiles` rejections and carried statements for missing pairs; `MarketAction.prob_ppm` on a continuous instrument **is** the up-probability at the shortest horizon, so the hive, `calibrator`, the stacker and the memory ledger work with no second code path. `forecast_recorded` gains the optional `horizons` and `price_ref_ticks` payload, `actions.v2.json` the optional top-level array | 8.1, 8.4, 9.2, 17.5, `actions.v2.json`, `journal.v2.json` |
| R158 | **The random walk is the baseline and its skill is zero by construction.** `up_probability_ppm = 500_000` and every quantile equal to the reference price; the `random_walk` family states exactly that and trades nothing; skill is the baseline's loss minus the agent's, so the baseline's skill is `0` identically, as `market_follower`'s is on a binary (decision D-12). A flat return scores `(brier(p, 1) + brier(p, 0)) // 2`, so the baseline scores `RANDOM_WALK_BRIER_MICRO = 250_000` on every outcome including a tie and a directional forecast is not rewarded for a price that did not move (AC-23) | 12.1, 17.5 |
| R159 | **The pinball loss is over five fixed levels, relative to the reference price.** `QUANTILE_LEVELS_PPM = (100_000, 250_000, 500_000, 750_000, 900_000)`; `pinball_micro = round_half_up(sum over levels of level * max(0, realised - q) + (PPM_ONE - level) * max(0, q - realised), 5 * price_ref_ticks)`, in micro-units of the reference price so that ES and EURUSD pool as relative errors; the baseline's pinball is the same formula with every `q` equal to the reference, and `pinball_skill_micro` is baseline minus agent. An agent that states no quantiles is scored on direction only and its row says so | 12.1, 17.5 |
| R160 | **A horizon resolves at the first bar where its realisation is public, and the hive releases it one bar later.** The reference is `last_price_bp` at the forecast bar (the close of the last completed bar), the realisation the close of the `h`-th completed bar after it, public at the open of bar `t_h`; the runner emits `forecast_resolved` in the settle phase of `t_h`, and the `forecast` hive entry of that horizon carries `visible_from_ms = t_h + interval_ms` in the instrument's own sequence, mirroring R12's "first bar strictly after". A horizon beyond the run's last bar of the instrument never resolves, is counted in `instrument_closed.n_forecasts_unresolved` and is not scored. `Hive.write_forecast` gains four keyword-only arguments and there is no `resolution` entry for a continuous instrument: the realised price is the tape | 9.2, 9.3, 10.4, 17.5 |
| R161 | **Calibration ledgers are per kind and horizon, and a tie is half a yes.** The memory's table and `calibration_table` bin `up_probability_ppm` into the ten deciles keyed `(kind, f"h{horizon_bars}", bin)` through the existing `CalibrationBin` with `category = kind`; `n_yes_x2` counts an up as `2` and a flat realisation as `1`, `yes_rate_ppm = round_half_up(PPM_ONE * n_yes_x2, 2 * n)`; `HorizonBucket.bucket` carries the `h<n>` strings, validated by `RE_HORIZON_BUCKET` while `HORIZON_BUCKETS` stays the four binary buckets (ruling R188); `ece_ppm` and `sharpness_ppm` are per slice and nothing is pooled across kinds or horizons | 10.3, 12.1, 12.2, 17.5 |
| R162 | **A claim is per `(kind, provider, horizon)` and its unit on a continuous kind is an `(instrument, week)` cell.** `claim_id = c-<dataset_hash[:8]>-<kind>-<provider>-h<horizon_bars>-<genome_hash[:16]>` (`h0` on a binary; the v2 form is still accepted by `journal.v2.json` and never written again); `open_sealed_test(..., kind="binary")` returns the ids of that kind and provider; `sealed_test_opened`, `claims/access.jsonl` and the claim record gain `kind` and `horizon_bars`; part 1 pairs the per-cell directional skill against the random walk (whose per-cell skill is `0`), `block_key` is the ISO week or the cluster, `n_markets >= CLAIM_MIN_MARKETS` counts cells, `K` counts candidates against `(dataset_hash, kind)`, and the permutation shuffles realised returns across instruments within a week (PRD v4 section 3). Folds keep their thirteen edges: a continuous instrument belongs to every fold whose months it has bars in, the run is clipped to those months and the forced flat closes it at the edge. The honest expectation, `no_demonstrated_edge` on most continuous claims, is recorded in the claim's note and reported as such (AC-25) | 2, 12.6, 12.7, 12.8, 17.6, 17.8, `journal.v2.json` |
| R163 | **Every leaderboard row, claim, `PerMarket`, `MarketResult` and `AgentResult` carries the asset class.** The row key becomes `(agent_id, kind, provider, horizon_bars, fold, category, hardness_tag)`; `LeaderboardRow` gains `kind`, `horizon_bars`, `vendor`, `n_units`, `n_quantile_forecasts`, `pinball_skill`; `PerMarket` gains `kind`, `horizon_bars`, `unit_key`, the two continuous losses, `baseline_pinball_micro`, `n_resolved`, `n_cash_events`; `MarketResult` gains `kind`, `vendor`, `last_price_ticks` with `outcome = -1` on a continuous instrument; `AgentResult` gains `pinball_skill`, `exposure_by_kind`, `n_cash_events`; `pnl_cents` includes every cash event and every event fill's fee; the two leaderboard and claims routes gain `?kind=&horizon_bars=`. Every addition is a defaulted field; `to_dict()` renders them, so the `results.json` of a v2 journal gains keys at their defaults, which moves no byte that exists because no run exists (ruling R199) | 12.3, 12.10, 12.11, 12.12, 17.6 |
| R164 | **What `pmx.journal` pins is declared now and promoted at gate G2, with the dataclasses.** D7's tests assert that the schema's `oneOf` equals `EVENT_TYPES` and that every event's phase enum equals its class's `PHASES`, so a schema ahead of the classes would fail the suite and refuse the journals the engine wave must write. Therefore: `cash_event_applied`, `instrument_closed` and `forecast_resolved` are declared under `$defs` and enter `oneOf` in the gate G2 commit that adds their three dataclasses; the `settle` phase of `order_placed`, `filled` and `fee_charged` enters the phase enum and the classes' `PHASES` in the same commit; `market_listed`'s `kind`, `vendor`, `symbol`, `tick_size_micro`, `point_value_micro`, `session_calendar_id`, `borrow_schedule_id`, `carry_schedule_id` and `forecast_recorded`'s `price_ref_ticks` and `horizons` are optional until then and the projection defaults them (`binary`, the provider, the id's slug, `100`, `1_000_000`, `"continuous"`, `null`, `null`), which is exactly what a v2 journal means. Every enum, pattern and bound widening that no class pins is applied now. `tests/test_contract_schemas.py` names the three pending events and fails the day one enters `oneOf` without its class or is dropped from `$defs` | 9.2, 17.3, 17.9, `journal.v2.json` |
| R165 | **The id and enum patterns of the two schemas C1b owns are widened here; those of the three it does not are contract issues.** `journal.v2.json` and `actions.v2.json` accept the seventeen providers of 17.8 in `marketId`, the widened `provider` enums, the claim id in both forms, `horizon_forecasts`, the new events, the widened `origin`, `reason`, `price_source` and `phase` enums and the tick and milli bounds; `market.v2.json` (`id`, `provider`, `currency`), `dataset.v1.json` (the instrument blocks of 7.8 and `files.path`) and `news.v1.json` (sources `edgar`, `fred`, `cboe`, kinds `filing`, `release`, codes `edg`, `fred`, `cboe`) are listed in 17.9 with their gates. The provider list uses ISO 10383 MIC codes for the equity and futures venues and `otcfx` for the FX book, so an instrument id says where a fee schedule comes from | 2, 7.3, 17.8, 17.9, `journal.v2.json`, `actions.v2.json` |
| R166 | **Every wave 3b file has one owner and the map says so.** F1 `binance.py`, `kraken.py`, `coinbase.py`, `bybit.py`; F2 `yahoo.py`, `frankfurter.py`, `ecb.py`; F3 `edgar.py`, `fred.py`, `release_calendar.py`, `cboe.py`, `data/calendars/releases.v1.json` and the four `fin_<topic>` lexicons; F4 `data/sessions.py`, `data/calendars/*.json`, `data/universe_finance.py`; D2 the two sealed Kalshi maps; A1 the six new families; R2f `analysis/cross_domain.py`; gate G3b `tests/e2e/test_e2e_1b_multi_asset.py` and gate G8 `test_e2e_2b_cross_domain.py`; C1b its four schemas. Section 14 gains the rows and amends E1, E2, E3, E5 and A1. The widening of `opportunity.v1.json` (`cross_domain`, `kinds`, `providers`, the currency list) is declared in 17.6 and applied by amendment C2, which opens the detector wave, so that C1's schema is edited by the amendment that owns the detectors | 13, 14, 17.6, 17.7 |
| R167 | **A bars-only tape is a real tape, and `min_trades` accepts it on its traded bars.** Kalshi publishes no settled print tape (`GET /markets/trades` answers `{"cursor":"","trades":[]}` for every settled ticker, probed on 2026-09-07 with and without `min_ts`/`max_ts`; the exchange-wide tape holds the last minutes only) while its candlesticks carry per-bar `volume` and `open_interest`. A provider whose tape is bars-only stamps `quality.tape_kind = "bars_only"`, `quality.n_trades = 0` and `quality.traded_bars` (bars with `volume_milli > 0`); 7.4's `min_trades` filter accepts a market when `n_trades >= min_trades` **or** `unique_bettors >= min_unique_bettors` **or** (`tape_kind == "bars_only"` **and** `traded_bars >= min_traded_bars`, a new `BuildConfig` field, default `20`); fills follow 8.6 on bar volume as before. This is distinct from R105's Polymarket case, whose tape carries no volume at all and which stays outside a built dataset. Without this ruling `min_trades` removed the whole provider (`removed min_trades=400`, `docs/BUILD_STATE.md` 5.2) and AC-3 had nothing to train on | 7.2, 7.4, 8.6, `market.v2.json` (17.9) |
| R168 | **The per-provider cap is applied after the window walk, by deterministic stratified sampling across the window's months.** Each importer used to cap from its own end of the walk, so 400 Kalshi markets settled in the first two days of the window and 400 Manifold markets in the last thirteen, every survivor landing in the sealed fold (`docs/BUILD_STATE.md` 5.3). `limit_per_provider` now applies to the full window's survivors: quota `limit // 12` per month of 7.7's edges, the remainder and any quota a thin month cannot fill going to the busiest months by pre-cap count (ties to the earlier month), the ids of a month drawn with `sample_without_replacement` from the one `dataset.subsample` substream of `RngTree(sample_seed_for(name))` with `sample_seed_for(name) = derive_seed(0, f"dataset/{name}") % SEED_SPACE` (`pmx.data.builder.stratified_cap` and `month_quotas`), providers in sorted order. Every fold of 12.7 is populated by construction, two builds of the same raw data draw the same markets, and the manifest records `counts.precap_per_provider_month` and `counts.n_bars_only` | 6.3, 7.4, 7.8, `dataset.v1.json` (17.9) |
| R169 | **The linker renormalises its weights over the evidence a market carries, and every provider populates `wiki_subjects` with a provenance flag.** On the first real dataset the 600-permille `shared_links` term was zero for effectively every market (392 of 400 Manifold markets and every Kalshi market had no subjects), no score could exceed 400, and 7 391 Current events items linked to nothing (`docs/BUILD_STATE.md` 5.4). A market with no `wiki_subjects` is now scored on keyword overlap alone at 1000 permille, and a market with subjects keeps the 600/400 split of the v2 formula whatever its keyword set. Kalshi subjects come from the sealed `src/pmx/lexicons/kalshi_series_subjects.v1.json` map plus title-derived candidates, Manifold subjects from the capitalised token runs of the question, deduplicated; each entry is marked `"stated"` or `"derived"` in the parallel, optional `wiki_subject_provenance` list of `market.v2.json` so a reviewer can tell them apart, and the flag does not enter the score | 7.2, 7.6, 13, `market.v2.json` (17.9) |
| R170 | **A Kalshi category comes from a sealed series-ticker map, with `other` as the fallback, counted.** Not one of the 227 381 settled rows in the build cache carries a `category` field, so every Kalshi market landed in `other` and the per-category leaderboard, the `specialist` family and memory's category priors were flat for the provider (`docs/BUILD_STATE.md` 5.5). `src/pmx/lexicons/kalshi_series_categories.v1.json` (D2) maps a **series ticker** (the part of a market ticker before the first dash) to one of the twelve categories of section 2, a series absent from the map is `other`, and the manifest counts how many kept markets fell back in `counts.n_category_fallback` | 2, 7.2, 7.4, 7.8, 13, `dataset.v1.json` (17.9) |
| R171 | **What C1b does not own is listed with its gate and nothing is lost.** Section 17.9 names every name of `pmx.types`, every widening of `market.v2.json`, `dataset.v1.json` and `news.v1.json`, the loader's walk, D7's event dataclasses, E2's `event_fill`, A3's `write_forecast` arguments, O1's and O4's claim changes, E4's within-week permutation, C1's `opportunity.v1.json` and the `.gitignore` and `pyproject.toml` lines, each with the gate or amendment that applies it. A section of this document is never a contract issue (R136), so no normative passage is deferred | 17.9 |
| R172 | **Two architecture rules join the nine.** Rule 10: nothing under `src/pmx/data/` imports `pmx.engine`, `pmx.agents`, `pmx.metrics` or `pmx.optimizer` (a seal that depended on the engine version would move with it). Rule 11: `in_session` is bound only in `src/pmx/data/sessions.py`, so "a bar outside its calendar does not exist" has one implementation. Both are green on the tree of 2026-09-08 and bind on the first commit that adds a file they cover | 17.7, `tests/test_architecture.py` |
| R173 | **One bar type and one price arithmetic for every kind.** 17.1 declared `InstrumentBar` with `_ticks` fields beside 7.2's `Bar`, while `MarketView.bars`, `quote_bar`, `envelope_bounds`, `historical` and `half_spread_ticks` were typed on `Bar` and 17.4's own body read `high_ticks`: every bar read in E1, E2 and E5 needed two code paths or an undeclared cast. The `_ticks` spelling is now the **file** shape only (`instrument.v1.json#/$defs/bar` and `trade`); the loader maps it onto `pmx.types.Bar` and `pmx.types.Trade` field by field (`open_bp <- open_ticks`, `yes_bid_bp <- bid_ticks`, `yes_ask_bp <- ask_ticks`, `open_interest <- open_interest_milli`, `price_bp <- price_ticks`), exactly as R148 keeps one event shape per name; `ContinuousInstrument.bars` is `tuple[Bar, ...]`, `bar_at` and `bars_before` sit on the `Instrument` base and `TRADE_SIDES` gains `buy` and `sell`. The binary-only arithmetic 17.9 claimed was amended in 16.1 and 8.6 and was not is amended now: `clamp_price(x, view)` (`clamp_price_bp` on a binary, `1..PRICE_TICKS_MAX` otherwise) replaces `clamp_price_bp` in step 4, rule 3 and `envelope_bounds`; `slippage_ticks` is `slippage_bp_per_pct * taken_pct` on a binary and `round_half_up(base * slippage_bp_per_pct * taken_pct, BP_ONE)` on a continuous kind; `size_milli = size * MILLI` and `filled // MILLI` hold on a binary only; rule 5 calls `fee_cents` with the milli size, `side`, `tick_size_micro` and `point_value_micro` on a continuous kind; `finalise_fill` and `truncate_for_cash` gain keyword-only `market_view`; `Fill.price_bp` loses `1..9_999`; `check_envelope` is exercised on a continuous view by E2. **Against the finding's remedy in one point**: the finding said a relative slippage equals the bp rule on a binary; it does not, because a binary's bp is a share of the payout and not of the price (10 bp at 6 327 would become 6), so the binary keeps the absolute rule and only the continuous kinds take the relative one | 7.2, 8.3, 8.6, 16.1, 17.1, 17.4, 17.9 |
| R174 | **`pmx.data.sessions` is D1's and exists at gate G2; `Execution` receives the run's calendars.** `SessionCalendar` and `in_session` had two owners (`pmx.types` in 17.9, F4 in 17.7 and 14) and F4 lands in wave 3b, after the wave whose `Calendar` (`open = listed and in_session`), `borrow_fee` (one event per session, days since the previous close) and loader (refuse a bar outside its calendar) need them, while rule 11 forbade E1 a copy. `src/pmx/data/sessions.py` (`in_session`, `next_bar_ms`, `load_calendar`, the synthesised `continuous` calendar and the exchange-calendar generator) moves to D1, applied by gate G2; `SessionCalendar` stays the `pmx.types` dataclass; F4 keeps `data/calendars/*.json` and `universe_finance.py`; sections 13, 14 and 17.7 say so and `docs/PLAN_V3_WAVES.md`'s F4 row is a contract issue in 17.9. `Execution.__init__` gains keyword-only `calendars: Mapping[str, SessionCalendar] | None = None` (preamble rule 2), `None` meaning the `continuous` calendar for every instrument, which is what a binary run passes | 8.6, 13, 14, 17.2, 17.7, 17.9 |
| R175 | **A corporate event applies at the last bar priced in the old regime.** `t_ms` of a `dividend`, `split` or `roll` is the first instant of the new regime (ex-date open, split effective open, first new-contract bar) and the tape already reflects it from `bar_of(t_ms)`'s open, so applying the event at that bar's settle phase paid a dividend to the buyer of the ex-date open, multiplied a position bought at the post-split open and netted a roll against new-contract fills; the 8.9 identity held and the economics were gameable by anyone with a corporate calendar. `applies_at(e)` (`pmx.engine.execution`) is `Calendar.prev_bar(i, bar_of(t_ms))` for those three kinds, the cum-date close, and `bar_of(t_ms)` for `funding`, `borrow_fee`, `carry` and `forced_flat`; an event whose application bar is outside the run is not applied. E2's cases gain a buy at an ex-date open that receives nothing and a buy at a split's effective open that is not multiplied | 3, 8.2, 8.6, 17.3 |
| R176 | **An engine event's `t_ms` is the last instant of the bar it applies at.** `forced_flat` was "the only event whose `t_ms` is the bar's own close", and `bar_of(t + interval_ms)` is the next grid point, not `last_bar(i)`; `borrow_fee` had no `t_ms` at all, and a session close on the grid (XNYS 20:00Z, hourly) would have made `bar_of(close_ms)` a bar that never exists, so no borrow fee was ever applied. `forced_flat.t_ms = last_bar(i) + interval_ms - 1`, `borrow_fee.t_ms` and `carry.t_ms` are the session's last bar `+ interval_ms - 1`, `bar_of(t_ms)` is then the applying bar, and `cash_event_id`, which hashes `t_ms`, is pinned on both in the contract fixture | 17.3, `cash_events.sample.json` |
| R177 | **The fx carry is a seventh, engine-origin kind.** 17.4 applied the swap "as a `funding` cash event named `carry` in `detail.role`", but `funding` is a data kind whose schema pins `origin: data` and a non-empty `source_url`, and a data-generated one would need the importer to read `CARRY_SCHEDULES` from `pmx.engine.fees`, which rule 10 forbids. `CASH_EVENT_KINDS` is `(funding, dividend, split, roll, borrow_fee, carry, forced_flat)`; `carry` carries `rate_ppm_per_day, days, mark_ticks`, is computed from the named `CarrySchedule` at the last bar of every session exactly as `borrow_fee` is, is signed (a long receives a positive rate and pays a negative one), and enters the schema's engine branch, the 17.3 tables, the fx row of the invariant table, `journal.v2.json`'s `cash_event_applied` enum and the fixture | 17.3, 17.4, 17.8, `cash_event.v1.json`, `journal.v2.json` |
| R178 | **`position_before` and `position_after` are defined for the fill-carrying kinds.** 17.3 said every event but `split` satisfies `position_after == position_before` and, three rows above, that a `forced_flat`'s residual "is journaled as `position_after != 0`" after a fill that closed the position; E2 could not write the property test. For `roll` and `forced_flat`, `position_before` is the position before the first event fill and `position_after` the position after the last one named in `order_ids`; the invariant reads `== position_before` for `funding`, `dividend`, `borrow_fee` and `carry`, `== split_position_milli(...)` for `split`, and `== the position_after of the last fill in order_ids` for the other two, in 8.9, 17.3, 9.2 and the schema description | 8.9, 9.2, 17.3, `journal.v2.json` |
| R179 | **A debit cash event may take cash below zero, and a debit balance funds nothing.** `funding`, `dividend`, `borrow_fee` and `carry` subtract cash with no truncation rule while the invariant kept `cash >= 0`: an agent that spent the proceeds of a short elsewhere and then met an ex-date left E2 two contradictory lines. A fill never takes cash below zero; a debit may. While `cash < 0` the agent carries a debit balance: `free_cash = max(0, cash - reserved)` is `0` so no opening fill lands, the event that took cash below zero expires every resting order of the agent with `order_expired.reason = "debit"` (a new enum value of `journal.v2.json`) so `reserved == 0`, closing fills and credits repay it, and ruin stays 8.7's rule on equity. `equity_marked.cash_cents` and `PortfolioView.cash_cents` are signed; no liability field is added because `equity = cash + positions_value` already carries the shortfall. The alternative, forcing ruin whenever cash dips below zero, was not taken: an agent long elsewhere with equity well above the floor is not ruined by a two-cent funding payment | 8.5, 8.7, 8.9, 9.2, 17.3, `journal.v2.json` |
| R180 | **The journal schema and the views are signed where the contract says the number can be negative.** R154 let equity fall below zero and the residual liability stay in `equity_marked` while `journal.v2.json` typed `equity_marked.equity_cents` and `agent_ruined.equity_cents` as non-negative and floored `drawdown_bp` at `-10000`, which `bp_ratio(equity - peak, peak)` passes with a negative equity. Both fields and `equity_marked.cash_cents` (R179) become signed integers, `drawdown_bp` keeps `<= 0` and loses its floor, `PortfolioView.cash_cents` and `equity_cents` are signed. **Against the finding's remedy**: no negative-equity row is added to `journal.backtest.jsonl`, which is a complete binary journal whose accounting invariant the suite asserts per agent and which no legal binary sequence can drive negative; the negative case is a document the schema test builds and validates instead | 8.3, 9.2, `journal.v2.json`, tests |
| R181 | **A continuous instrument's `MarketView` shows neither its delisting nor its last bar.** 9.2 put `delisted_at_ms` in `market_listed.close_at_ms`, 8.3 kept `close_at_ms` required in every view and 5.4 called it always visible, while 7.9 forbade `delisted_at_ms`; `tradable` at `last_bar(i)` (false while the instrument is open) announced the end one bar ahead. `MarketView.close_at_ms = 0` and `MarketView.tradable = open(i, t)` on a continuous instrument (the engine still refuses every agent fill at `last_bar(i)`), `last_bar(i)` joins 7.9's list and the clock test's key set, and E1's poisoned-future test injects a `delisted_at_ms` and a `last_bar`. The journal's `market_listed.close_at_ms` keeps `delisted_at_ms`: a journal is not an observation | 5.3, 5.4, 7.9, 8.3, 14, 17.2 |
| R182 | **The sealed months of a continuous price path are reachable from `claims.py` and nowhere else.** A binary's sealed guarantee is structural (a sealed id is never handed out) and rule 3 scans for the one accessor; a continuous instrument belongs to every fold, so `Dataset.market` handed the whole tape, sealed months included, to every consumer and rule 3 was vacuous. `Dataset.market` returns a continuous instrument clipped at `manifest.split.validation_end_ms` (bars, trades, cash events); `Dataset.sealed_market` returns the whole record and its name joins `open_sealed_test` and `_sealed_ids` in architecture rule 3's regex, so only `optimizer/folds.py` and `optimizer/claims.py` may spell it and the test binds today. `quality` stays a whole-window build statistic, because 7.4's filters need the whole life as they do on a binary, and is never shown to an agent | 7.2, 7.9, 17.2, 17.9, `tests/test_architecture.py` |
| R183 | **An applied cash event is visible; an unapplied one never is.** 17.7's `carry` family read "the last funding rates from the agent's own portfolio history" while 17.3 and 7.9 banned every `CashEvent` field without exception and no view carried one, so A1 could not implement it. R151's blanket ban is replaced by the as-of rule every other datum obeys: an event whose application bar has completed (`applies_at(e) + interval_ms <= now_ms`) is the venue's published past and appears in `MarketView.cash_events` (`CashEventView(kind, t_ms, applied_at_ms, detail)`, the last `CASH_EVENTS_VIEW_MAX = 30` data events of the instrument, D1's defaulted field); one whose application bar has not completed never appears, so an announced dividend is hidden until the cum-date close. 7.9 and E1's poisoned-future test carry both halves | 5.4, 7.9, 8.3, 17.3, 17.7 |
| R184 | **`prob_ppm` synthesises the shortest horizon when no pair states it.** 17.5 carried a missing pair as the random walk and refused a `prob_ppm` that disagreed with the shortest horizon, so every family that emits `prob_ppm` and `horizon_forecasts = ()` (`trend`, `revert`, `breakout`, `volume`) was `action_rejected(bad_prob)` on every bar of every continuous instrument. When `horizon_forecasts` has no pair for `(market_id, shortest horizon)` and a `MarketAction` on the market exists, the runner builds the pair from `prob_ppm` with `quantiles_ticks = None`; only a pair that is present must agree with `prob_ppm`, else `bad_prob`; 8.4, 17.5 and the `horizon_forecasts` description say so | 8.4, 17.5, `actions.v2.json` |
| R185 | **The session rule binds a `ContinuousInstrument` only, and `continuous` is synthesised, never a file.** 17.2 made every binary carry `session_calendar_id = "continuous"`, defined that calendar as the resolution window as one session and refused a bar with `in_session == false`, which rejected the ninety `opened_early_days` of every existing binary dataset; and no dataset had a `calendars/continuous.json` for `Dataset.calendar` to return. A binary keeps 7.2 verbatim and its file is never checked against a calendar; the loader synthesises `continuous` as one session `[0, INT63_MAX)`, refuses a `calendars/continuous.json` (`session_calendar.v1.json` refuses the id), and a calendar file's `window` must cover every bar of every instrument naming it | 5.2, 7.2, 17.2, 17.8, `session_calendar.v1.json` |
| R186 | **`MarketMeta` and the canonical order are defined for a continuous instrument.** R144 added only `MarketMeta.kind` while `sort_markets`, `block_key`, `DatasetSplit.fold_of` and `Folds.train_ids` read `resolved_at_ms`, `MarketResult.outcome = -1` was declared and `MarketMeta.resolution` was not, so E1, E2, E5 and O1 would each have invented a value and broken byte determinism across packages. On a continuous instrument `created_at_ms = listed_at_ms`, `resolved_at_ms = delisted_at_ms` when set else the dataset's window end, `close_at_ms = resolved_at_ms`, `resolution = -1`, `event_key = None`, `hardness_tags = ()`, `fold = "all"`, `n_bars` the file's bar count; section 3's `(resolved_at_ms, id)` order stands unchanged over those values, `block_key` on a continuous row is the cell's week, and `Folds` lists a continuous id in every fold whose months intersect `[created_at_ms, resolved_at_ms)` | 3, 7.2, 7.7, 12.4, 12.7 |
| R187 | **E1 exposes `closing_ids`, `last_bar`, `next_bar` and `prev_bar`.** 8.2 had the runner call `force_flat` and emit `instrument_closed` "at `last_bar(i)`" while `BarSlice` carried four tuples and `Calendar` three members, none of which said where the closing set came from, and `bars()` was still commented "dense on config.interval_min" against 17.2's union calendar. `BarSlice.closing_ids: tuple[str, ...] = ()` (the instruments with `closes(i, t)`), `Calendar.last_bar(market_id) -> int`, `Calendar.next_bar(market_id, t_ms) -> int | None` and `Calendar.prev_bar(market_id, t_ms) -> int | None` are E1's one implementation, which the queue drain, `decided_at_ms`, `applies_at` and the forced flat read; the `bars()` comment reads the union | 5.3, 8.3, 17.2 |
| R188 | **Every name the engine and agent waves import is declared once, in one file.** `MarketView.kind` and its scales were E1's in 17.5 and D1's in 17.9 while 8.3's listing showed none of them; `basis` and `pairs` needed `underlying_id` and `twins` no view carried; `default_horizons_bars` was E3's in 17.5 and D1's in 17.9; `BuildConfig.__post_init__` refuses a provider outside `PROVIDERS` and a source outside `NEWS_SOURCES`, neither of which 17.9 widened, so every F1 and F3 build would have failed `InvalidConfigError`; `HORIZON_BUCKETS` "gained" per-run strings although it is a module constant. 8.3's `MarketView` gains eight defaulted fields (`kind`, `tick_size_micro`, `point_value_micro`, `session_calendar_id`, `hours_to_next_bar`, `underlying_id`, `twins`, `cash_events`), D1's and filled by E1; `default_horizons_bars` is `pmx.types`'; the 17.9 row names `PROVIDERS`, `VENDORS`, `CURRENCIES`, `NEWS_SOURCES`, `NEWS_KINDS`, `NEWS_KIND_BY_SOURCE`, `NEWS_CODE_BY_SOURCE`, `RE_NEWS_ID`, `RE_LIVE_FORECAST_ID`, `TRADE_SIDES`, `DATA_CASH_EVENT_KINDS`, `INT63_MAX`; `RE_HORIZON_BUCKET = ^(30d|7d|2d|0d|h[0-9]{1,5})$` validates a bucket string and `HORIZON_BUCKETS` stays the four binary buckets | 8.3, 10.3, 12.11, 17.5, 17.8, 17.9 |
| R189 | **PRD v4 1.2 is corrected by a contract issue, and R145 no longer says the PRD is not amended.** R145 set `BINARY_TICK_SIZE_MICRO = 100` against the PRD's `10_000` and R146 read its rounding sentence, so the PRD asserted a false identity while the preamble says the PRD wins on a functional point. The PRD defers "the conversion formulas, the rounding rule and the overflow bounds" to this amendment, so the value is this document's to decide and the preamble's rule is not engaged; its 1.2 row is nonetheless wrong on its face and is corrected (binary row `100`; "one rounding, at the end, against the agent for a cash movement; round half up for a score or a quantile"; revision 1.1 citing R145, R146, R189) as a contract issue for gate G2 in 17.9, because `docs/PRD_V4_MULTI_ASSET.md` is not a file this amendment owns | 15.9, 17.9 |
| R190 | **The continuous permutation null permutes `realised_sign` among the forecasts that share a bar and a horizon within a week.** 17.6 permuted "the `realised_sign` and `price_realised_ticks` of the cells of one week across the instruments of that week", but a cell aggregates many forecast bars, instruments in one week have different bar counts (7 XNYS bars a day, 24 crypto bars, 5 FX days), so no one-to-one reassignment existed, and a pinball loss over prices in different units is meaningless; 12.4's `permutation_null` was binary-shaped. For each permutation the `realised_sign` values of the forecasts made at the same bar `t` for the same horizon `h` are permuted across the week's instruments that carry a forecast at `(t, h)`, unmatched forecasts stay, the per-cell directional skill is recomputed, `price_realised_ticks` is never shuffled and `pinball_skill` has no permutation part; `permutation_null` gains keyword-only `realised_signs` and `bar_keys`. **Against the finding's first remedy**: permuting per-cell skill values across instruments is not a null of no skill, because the exchangeable object under the random-walk hypothesis is the realisation, not the score | 12.4, 17.6, 17.9 |
| R191 | **The per-instrument score is the plain mean, stated as a rule.** 17.5 derived the plain mean from 12.1's time weighting ("equally spaced on its sequence"), which is false on a session instrument: a Friday-to-Monday `w_i` is sixty hours and 12.1's weighted mean differs from the plain one. The plain mean is the rule (forecast bars weigh equally; the session gap is the tape's) and the appeal to 12.1 is deleted | 17.5 |
| R192 | **`decided_at_ms` is the instrument's previous bar.** 9.2 spelled it `bar_ms - interval_ms`, 8.2 drained "the queue accepted at `t - interval_ms`" and 8.6 the same, all three wrong for a session instrument under 17.2's "the instrument's next bar" (a Friday decision fills on Monday). The three read "the instrument's previous bar (`bar_ms - interval_ms` on a `continuous` calendar)", 16.2 says every `t + interval_ms` of the subsection is read that way, and E5's last-bar test reads "no `order_placed` carries a `decided_at_ms` equal to its instrument's last actionable bar or later" | 8.2, 8.6, 9.2, 16.2, 17.2 |
| R193 | **The events of one bar apply kind first.** `(t_ms, kind order, cash_event_id)` made "a split on the same bar as a dividend applies after it" hold only when both carried one `t_ms`; a dividend stamped 13:30Z and a split stamped 09:00Z applied split first and the dividend was paid per post-split share against a pre-split `dividend_micro`. The order inside a bar is `(kind order in CASH_EVENT_KINDS, t_ms, cash_event_id)`, so the stamp never decides the order of two events of one bar; an instrument file stays chronological by `(t_ms, kind order, cash_event_id)` and execution regroups per application bar; section 3 carries the row | 3, 8.6, 17.3 |
| R194 | **`CalibrationBinView` carries `n_yes_x2`.** 17.5 stored `n_yes_x2` in the ledger and carried it "in the existing `CalibrationBinView`" whose fields are `(category, horizon_bucket, bin, n, n_yes)`, so a consumer computing `n_yes / n` on a continuous slice was off by two or lost the tie. The view gains `n_yes_x2: int = 0` (`2 * n_yes` on a binary slice; `n_yes = n_yes_x2 // 2` on a continuous one), and every ratio reads `n_yes_x2` over `2 * n` through one spelling in `pmx.metrics.calibration` | 8.3, 12.2, 17.5 |
| R195 | **`forecast.v1.json` is the common core of the three forecast shapes, and the live line carries it.** The schema said it was "the shape of the hive's forecast payload, of `live/forecasts.jsonl` and of the horizons field of `forecast_recorded`" while none of the three matched it. Its description names what it is: the record `tests/test_contract_schemas.py` validates, whose `horizons` items are `forecast_recorded.horizons` items and, with `price_ref_ticks`, the hive payload of 17.5, and whose `kind`, `bar_ms`, `price_ref_ticks` and `horizons` fields `live/forecasts.jsonl` gains beside its own (9.5) when L1 generalises the line at gate G6 | 9.5, 17.5, `forecast.v1.json` |
| R196 | **The notional cap is checked once, at the execute phase.** 8.4 listed `bad_size` for a notional over `NOTIONAL_CENTS_MAX` among the decide-phase reasons while 17.1 and 8.6 had `Execution` refuse it as `order_rejected(bad_size)`, so the projection's rejection counts differed by phase. The execute phase keeps it, because the price is known there: `p` is the limit price of a limit order and `bar.high_bp`, the largest price the envelope can print, for a market order; 8.4's clause is deleted | 8.4, 8.6, 17.1 |
| R197 | **A schedule row names one provider.** `usequity-zero-2026-09` listed `xnys, xnas, arcx` while `FeeSchedule.provider` is one provider, the id pattern carries one and an instrument's `provider` names "the venue whose fee schedule applies"; the borrow schedule `usequity-borrowgc-2026-09` had the same shape. Three fee rows (`xnys-zero-2026-09`, `xnas-zero-2026-09`, `arcx-zero-2026-09`) and three borrow rows (`xnys-borrowgc-2026-09`, `xnas-borrowgc-2026-09`, `arcx-borrowgc-2026-09`) ship with the same numbers, and the AAPL fixture names the `xnas` pair | 17.4, `instrument.xnas-aapl.json` |
| R198 | **A roll's reopening leg is truncated like any fill, and a residual after `instrument_closed` is marked at the last price.** 17.3 said a position "never earns or loses the gap, it pays two fills" without saying what happens when cash cannot pay the second one, and the residual short after `instrument_closed` had no mark price for an instrument with no more bars. The reopening leg goes through `truncate_for_cash` and the short-notional rule, its residual is in the leg's `unfilled_size` and `unfilled_reason` and in `cash_event_applied.position_after`, a residual position after `instrument_closed` is marked at `instrument_closed.last_price_ticks` until run end, and E2's cases gain a roll with a positive gap on an agent with no free cash | 8.6, 8.7, 17.3 |
| R199 | **Three binary-only sentences are corrected.** `ClaimRefusedError` (13.1) keys on `(dataset_hash, kind, provider, horizon_bars, genome_hash)` as 12.8 does; `RunProjection.per_market` is sorted by `(agent_id, market_id, horizon_bars, unit_key)`, a total order once a continuous `(agent, instrument, week, horizon)` has its own row; and R163's "byte-identical" claim is replaced by what is true, that `to_dict()` renders the defaulted fields, so a v2 journal's `results.json` gains keys at their defaults and no byte that exists moves because no run exists | 12.11, 13.1, 15.9 |

### 15.10 Amendment C1c (the discovery layer of `docs/PRD_V5_DISCOVERY.md` and the two reviews)

C1c writes section 18 and 7.14 after gate G2 and before the agents wave (`docs/PLAN_V3_WAVES.md` lots 5b
and 6), so that S1, S2, F5, DS1, DS2, FM1, A1..A6 and O1..O4 are built once against the sensor gene, the
hypothesis layer, the minute grid, the workflow genome, the cohort and the two reviews together.
**R230 to R246 are the section 18 rulings**, **R247 to R259 land decisions D-R1 to D-R14** of
`docs/REVIEW_2026-09-08.md` (D-R8 is R238, the promotion ruling, because the decision is the
mechanism), **R260 to R273 land decisions D-S1 to D-S14** of `docs/REVIEW_2026-09-09_SCALE_TAGS.md`, in
the form section G of that review corrected (D-S11, D-S12 and D-S14 supersede D-S1 and D-S9 as first
written, so the corrected form is what is normative and the first form appears nowhere), and **R274 and
R275 carry gate G2's four declared-not-applied shapes forward** and state what this amendment leaves
alone. The numbering starts at R230 because gate G2's audit pass took R228 and R229 (15.3). Every
normative passage this amendment changes lives in a file C1c owns and is amended in place (ruling R136);
what is left is code in another package's file, listed in 18.8 with the package that applies it. Where a
value has a measurement behind it, the ruling cites it; where it has none, the text says it is a default the
first build reports against. **R276 to R302 are the amendment's own arbitration**: one critic attacked C1c
with twenty-four findings, and every one of them was verified in the text before it was fixed, upheld or
refuted, the pattern 15.8 and 15.9 followed. Nine of them are resolved **against the fix the critic
proposed** and say why in their ruling (R276, R282, R283, R286, R289, R290, R291, R296, R297), one goes
**beyond** its proposal (R292), three are upheld in substance with their reasoning corrected (R276, R282,
R292), and four rulings answer questions the amendment itself flagged and the critic passed over (R299 to
R302). Where an
arbitration ruling changes what an earlier ruling of this section said, that earlier row is amended in
place and names the ruling that superseded it, so no two rows of this table disagree (ruling R136 applies
to a ruling as it applies to a section). **No ruling here moves a byte of a journal a run has written: no
such run exists, `ENGINE_VERSION` stays `2.0.0` and `CONTRACT_VERSION` stays `"2.0"` (R275 and R302, the
trigger of R227 and 13.2 unchanged).**

| # | Ruling | Sections |
|---|---|---|
| R230 | **The sensor hook is normative and the tape is mandatory.** `build_observation(..., sensors=genome.sensors)` is the signature E1 shipped and 8.3 now declares it: `None` means every sensor and is byte-identical to the builder without the keyword, a set narrows by **subtraction** over what the as-of filters produced, and an unbought field is **absent** (no slot value, no key in the payload), never zeroed and never `None`, so no sensor set can widen an observation and the as-of law needs no second proof. `Genome.sensors: tuple[str, ...]` is sorted, unique, always rendered by `to_dict()` and **always contains `tape`**: a genome that omits it is refused (`InvalidConfigError`) rather than given a view without a price, because every family of 10.5 reads `last_price_bp` and a tape-less view would be a second observation shape for a diet nobody asked for. `FamilySpec.required_sensors` names what a family reads and no operator produces a genome that lacks one. The catalogue is closed at the fifteen sensors of PRD v5 1.1, with the PRD's costs verbatim and lags that are defaults | 8.3, 10.1, 18.1 |
| R231 | **A run records the diet it ran under.** `Observation.sensors` (the resolved set, sorted, the full `SENSOR_NAMES` when everything was bought), `observation_built.sensors: list[str]`, `run_started.sensor_catalogue_hash` and `RunConfig.sensor_catalogue_hash: str = ""` (`""` meaning the shipped catalogue; a non-empty value that differs from `CATALOGUE_HASH` is `InvalidConfigError`, the `liquidity_params_hash` pattern of R112) are declared. The runner passes `genome.sensors` where it passes `None` today (BUILD_STATE 8.7). The two journal fields move every future journal and no run exists: they are applied by the first engine lot together with R213, R214, R217 and R221 (R274), and `journal.v2.json` declares them optional until then (R164's discipline) | 8.1, 8.3, 9.2, 18.1 |
| R232 | **`SensorAbsentError` joins 13.1.** Reading an unbought field raises `SchemaError` today for want of a better fit (E1's hook report); the taxonomy gains `SensorAbsentError(field, unsensed, view)`, raised by the sensed views of the observation builder and by nothing else, because "the agent did not buy this" is a distinct failure from "a file failed its schema" and a test that pins one must not pass on the other. `pmx.errors` is D1's and S1 adds the class and switches the raise by the agreement recorded in section 13; E1's tests that pin `SchemaError` on an unsensed read are corrected to the contracted class in the same commit, which is a test disagreeing with the contract and not a weakening | 8.3, 13.1, 18.1 |
| R233 | **`cash_events` sits under `volume_profile`, the hive is split between its two sensors, and three gates go one level down.** The v5 catalogue names no sensor for `MarketView.cash_events`; PRD v5 1.1's `volume_profile` row reads "volume z-scores, open interest, funding" and 17.7's `carry` family reads funding from `cash_events`, so applied cash events (funding, dividends, splits, rolls) are that sensor's, and `carry` requires it. `Observation.hive` is present when either hive sensor is bought: `hive_reputation` gates `HiveView.reputations`, `hive_insights` gates the rest (`insights`, `lessons`, `resolutions`, `forecasts`, `prev_bar_forecasts`). The hook gated whole fields only; three nested gates are declared with the same absence semantics (`SensedBar` for `volume_milli`, `n_trades`, `open_interest` under `volume_profile` and `yes_bid_bp`, `yes_ask_bp` under `microstructure`; `SensedHiveView`; the `news` tuples filtered by `SENSOR_BY_NEWS_SOURCE`). A `ResearchRequest` whose kind's sensor is not in the diet is `action_rejected(bad_research)`; the grant still costs research units: the research budget prices grants, the sensor budget prices standing subscriptions, and the hook's question ("which one prices a grant") is answered | 8.3, 8.4, 18.1 |
| R234 | **A `SensorBlock` is a slice of `features.v1`.** Every sensor is a pure function from the as-of views to a fixed-width integer block whose layout is a tuple of 16.5's `FeatureSpec` with `source` the sensor name and `asof_only = True`, plus `features_v1_index`; `features.v1` is unchanged and each of its thirty-one non-portfolio fields belongs to exactly one block through that index, the blocks outside it (seventy-five names in all on the shipped fixture) await a `features.v2` of R3a's before a torch policy sees them, a missing input takes `spec.sentinel` (a field, ruling R285 superseding this ruling's "the sentinel its description names, `lo` by default"), and `pmx.rules.vocabulary.FEATURE_NAMES` is exactly the union of the blocks' names, so a rule's predicate can only name a sensor feature. Blocks are computed in `observe`, never journaled (a projection of the observation) | 16.5, 18.1 |
| R235 | **The sensor budget is a per-bar cap with the research-penalty rule generalised, and the diet is a fourth archive axis.** `diet_cost_units(genome)` is the sum of the diet's costs per bar; `EvolutionConfig.sensor_budget_units` (default `SENSOR_BUDGET_UNITS_DEFAULT`, the catalogue's `17` plus the one proposal unit, `18` since ruling R281) is a fresh genome's allowance and a cap the diet must fit, carried into a run by `RunConfig.sensor_budget_units` and `sensor_budget_by_agent` (R281); an agent whose `skill_lb_micro` did not improve and whose diet costs more than `0` loses `SENSOR_PENALTY_UNITS = 2` next generation (`generation_closed.sensor_budget_next`); a child that does not fit its allowance takes the deterministic **sensor drop** (`op = "sensor_drop"`: the most expensive non-`tape`, non-required sensor first, ties by name descending) and one that cannot fit is `culled_by_budget`. Fitness stays net of nothing: a sensor cost never moves a cent. `Descriptors.diet_class` (`0` tape and market, `1` news, `2` hive) is an archive axis with three bins, `ARCHIVE_CELLS = 144`, `cell_key = f"t{i}-c{j}-a{k}-d{l}"`, and AC-6's forty percent is read against `ARCHIVE_CELLS_REACHABLE` and not against 144 (ruling R297 superseding this ruling's flat "58 cells"), which the first evolution reports against and 14.1's D-7 records as amended. `candidate_scored` gains `diet_cost_units`, `sensors` and `n_rules_proposed`. The two numbers are defaults | 9.4, 12.5, 12.6, 12.11, 14.1, 18.1 |
| R236 | **A rule is a record in a closed vocabulary, content-addressed, and a bad one is `RuleRefusedError`.** `Rule(rule_id, author_kind, author_id, born_at_ms, scope, condition, claim, horizon_bars, min_support, family_id)` with `Predicate(feature, op, value)` over `FEATURE_NAMES` and `PREDICATE_OPS`, at most `RULE_PREDICATES_MAX = 3` predicates sorted by `(feature, op, value)`, `RuleScope(kinds, providers, categories, tags, cohorts)` and `RuleClaim(kind, direction, magnitude_bp, factor_ppm)`; `rule_id = "ru-" + sha256(canonical_json([scope, condition, claim, horizon_bars, min_support]))[:16]` is author-independent so two authors of one statement produce one rule (the first proposal in journal order is the author of record). Categorical facts (category, provider, kind, tag, cohort) are **scope**, predicates are over integer sensor features only, so the grammar is closed and every rule is evaluable on every bar of every dataset by `Rule.fires`. What a claim measures per matched row is the table of 18.2 (integers, bp), the effect is the block bootstrap of 12.4 over those rows, and the sign is what is tested, not the magnitude. `rule.v1.json` and `rule.sample.json` are this amendment's | 13.1, 18.2, 18.7 |
| R237 | **Three authors, one ledger, one tester.** The symbolic miner (deterministic beam search on the fit fold, `RULE_MINER_BEAM = 32`, at most `RULE_MINER_CANDIDATES_MAX = 10_000` enumerated per family, thresholds at `RULE_THRESHOLD_QUANTILES_PPM`, no substream), an agent's `Actions.propose_rule` (at most one per bar and `RULE_PROPOSALS_PER_GENERATION_MAX = 20` per generation, journaled `rule_proposed`, `action_rejected(scope="rule", reason="bad_rule")` when invalid and `reason="budget_exceeded"` when unaffordable, `RULE_PROPOSAL_COST_UNITS = 1` sensor unit of that bar; rulings R281 and R300) and every detector of 16.4 whose finding is statable in the vocabulary (`author_kind = "detector"`) feed the same ledger and go through the same tester, so hand-written and discovered knowledge are compared on one footing. `actions.v2.json` gains the optional `propose_rule`; `RejectReason` gains `bad_rule` | 8.4, 9.2, 16.4, 18.2 |
| R238 | **Decision D-R8: pre-registered families, Benjamini-Hochberg within a family at five percent, out-of-time replication as the primary criterion, and visibility that follows the data.** Bonferroni over the miner's millions of candidates kills everything or invites cheating, so: every rule of a generation is assigned to a `HypothesisFamily(family_id, dataset_hash, generation, fit_fold, replicate_fold, template, n_candidates, n_screened, fit_t1_ms, registered_at_ms)` (ruling R284 put the data in the id, which this ruling had keyed on `[generation, template]` alone) whose `FamilyTemplate(scope_keys, features, claim_kind, horizon_bars, author_kind)` is the grammar of what may vary, registered by a `family_registered` event **before** any replicate-fold read (the tester refuses a rule whose family has no earlier registration in the same journal or ledger); `n_candidates` is journaled whatever became of them. The fit-fold screen keeps the candidates whose claim held; each survivor's one-sided `p_value_ppm` on the **replicate** fold comes from `rule_permutation_p_ppm` (12.4, ruling R282 replacing this ruling's call into `permutation_null` with the rule's implied forecasts), on the same statistic the promotion tests, with the `(b + 1) / (B + 1)` estimator and `permutations` scaled to the family; `benjamini_hochberg(p_values_ppm, *, q_ppm = FDR_Q_PPM = 50_000)` over the family's `n_screened` p-values (`p_(k) * m <= k * q`, integers) marks `fdr_passed`. A rule is **promoted** iff its claim holds on the replicate fold **and** `fdr_passed`; one that passes the FDR step and fails replication is a recorded negative result, never an `Insight`, still counted in its family, and its content is a duplicate the tester will not re-test on the same fold pair. The fold pair is the **rolling pair** `(months 1..k, month k+1)`, clipped to the pairs whose replicate month ends at or before `train_end_ms` (ruling R277), inside evolution, or the **headline pair** `(train, validation)` for L1 and claims; `fit_t1_ms` is the replicate fold's last bar and an `Insight` is visible from `fit_t1_ms + interval_ms`, never earlier, mirroring 5.4's release rule. **PRD v5 2.3 step 3 and E2E-5a are corrected in place**: "`visible_from = now + one bar`" and "promotion on validation, then trades it on validation" would let a rule fit on validation outcomes be traded on the same fold; the fixture promotes on the rolling pair and trades out of time on validation, and PRD v5's revision history carries a 1.1 entry. `benjamini_hochberg` is E4's name in 12.4, added by S2 by the agreement of section 13 | 9.4, 12.4, 12.6, 18.2, PRD v5 |
| R239 | **An `Insight` is the promoted rule with its records, the live record demotes it, and the author is paid in rank and in allowance.** `HiveEntry(kind="insight")` carries the rule, the fit and replicate intervals, `p_value_ppm`, the family and the live record; `HiveView.insights` carries, for the agent's open markets, the undemoted insights the agent's diet can read (`readable_by`, ruling R279) whose rule **fires at `now_ms`**, at most `HIVE_INSIGHTS_VIEW_MAX = 50`, ranked by `(-lower_bp, rule_id)`, a pure function of the bar; the live record it carries is as-of (ruling R276); `Hive.write_insight` and `Hive.demote_insight` are the two engine-only writers; `hive_written.kind` gains `insight`. Demotion fires when `live_support >= RULE_LIVE_MIN_SUPPORT = 30` and `live_interval.upper < 0`, or when the author's reputation in the dominant category is negative while the live lower bound is not positive; a demoted rule is never re-promoted. The author of a promoted rule gains `RULE_AUTHOR_BONUS_MICRO = 5_000` on `skill_lb_micro` **for ranking only** (never in a recorded interval or a claim) and `RULE_AUTHOR_SENSOR_BONUS_UNITS = 2` of allowance; a rejected or demoted rule costs its author `SENSOR_PENALTY_UNITS`; `generation_closed.rule_rewards` records every entry. The poisoning test gains a false insight from a negative-reputation author. The three numbers are defaults | 9.2, 9.4, 10.4, 12.6, 18.2 |
| R240 | **`rule_follower` is a belief family and `llm_belief` is a step kind.** `rule_follower` (`min_lower_bp: 0..2000 (50) [100]`, `weight_permille: 0..2000 (50) [1000]`) states `ppm_from_bp(last + sum over firing insights of claim.direction * (lift_bp * weight_permille // 1_000))` clamped (ruling R280 added `claim.direction` and the `bias`-or-`drift` filter this ruling omitted), where the sum runs over `HiveView.insights` of the market with `lower_bp >= min_lower_bp` and a `bias` or `drift` claim, and the random walk or `ppm_from_bp(last)` when none fires; `required_sensors = {hive_insights}`. `calibrator` and `newsbayes` take a firing insight's `lift_bp` as a prior shift when `hive_insights` is in the diet, and the hive-insight sensor is the only channel: no family reads the ledger files. `llm_belief` is 18.4's step kind for an LLM seat and obeys 11.3 whatever the graph | 10.5, 18.4 |
| R241 | **The minute grid is the third grid and a source enters it only if its stamp is fine enough.** `INTERVALS_MIN = (1, 60, 1_440)`, the schemas' `interval_min` enums gain `1`, `bar_of` and the density rule are unchanged, and a minute dataset is a separate dataset built per instrument on demand (`pmx data build --interval-min 1` refuses a bare provider: `BuildConfig.instruments` or `kalshi_series_allow_list` carries the list, ruling R298). `SOURCE_GRANULARITY_MS` and `SAFETY_LAG_MS_BY_SOURCE` are `pmx.types` tables; a source enters a `interval_min = 1` dataset iff its granularity is at most `MINUTE_SOURCE_GRANULARITY_MAX_MS = 15 * MS_PER_MINUTE` (`BuildConfig.__post_init__` refuses otherwise), so no Wikipedia day page, Wayback capture or daily VIX print ever carries a minute hypothesis; daily and hourly datasets admit every source (D-R5). The lag becomes **per source**: `visible_from_ms = published_at_ms + lag(source)` with `lag` read from `manifest.news.safety_lag_by_source` when present and `manifest.safety_lag_ms` otherwise, recomputed and refused on mismatch by the loader as today, so a dataset built before this amendment recomputes to the same bytes. Hacker News is `NEWS_SOURCES` entry `hn` (kinds `story` and `comment`, id code `hn`, `published_at_ms = created_at_i * 1_000`), fetched by F5 through the one HTTP client; `pmx.data.news.timestamped` is the one implementation of the admission rule. Funding and liquidation instants are `CashEvent`s, never news. The lags are defaults the first minute build reports against | 5.1, 5.2, 5.5, 7.3, 7.4, 7.8, 18.3 |
| R242 | **The minute event study emits rules.** On a minute dataset R2a runs at `NEWS_LEAD_MINUTE_HORIZONS_BARS = (1, 5, 10, 30, 60)` per source and story feature and emits each finding as a `drift` or `volatility` rule with `author_kind = "detector"` beside its `OpportunityEvent`, tested by S2's tester; AC-28's planted ten-minute drift is such a rule with a positive lower bound on the replicate fold | 16.4, 18.3 |
| R243 | **A workflow is a bounded DAG over a closed step catalogue, and the linear genome is its degenerate case.** `Genome.workflow: Workflow | None`, always rendered, `None` meaning `linear_workflow(genome)` (`sense -> features -> belief -> overlay... -> sizing -> actions` from `(family, inner, members)`), so no genome hash of a linear genome depends on the graph and every family and composition of 10.5 is a valid workflow. `STEP_KINDS` are nine, `Step(kind, ref, params)`, `Workflow(steps, edges)` in topological order with `from < to` as the canonical form; `WORKFLOW_STEPS_MAX = 12`, `WORKFLOW_DEPTH_MAX = 8`, `WORKFLOW_WIDTH_MAX = 4` (defaults), exactly one `sense` and one `actions`, at least one belief, at most one `sizing` and one `propose_rule`, two beliefs into one sizing combined by the unweighted mean. `workflow_step_executed` is one event per `(agent, bar, step)` in `decide`, digest only (`output_sha256`, `n_out`), filled from the `StepTrace` tuple `run_workflow` returns (12.11, ruling R278), emitted **only** for a genome whose `workflow` is not `None`, so no v2 journal gains a byte; structure mutation that breaches a bound returns the parent unchanged. `workflow.v1.json` and `workflow.sample.json` are this amendment's | 9.2, 10.1, 18.4 |
| R244 | **Three evaluation additions, all projections.** The knowledge-transfer re-test (`rule_tested(stage="transfer")` per provider, category and kind outside the scope, never promoting and never widening a scope), the rule-adjusted claim (`rules_used` with each insight's live record at claim time) and the sensor ablation (`--ablate-sensors`: one run per sensor of the champion's diet with that sensor removed, `skill_drop_micro` from the two `results.json`, never from two hashes, in the claim's `sensor_ablation` table and served by `GET /claims/{claim_id}`); U3 shows the ledger and the table (AC-30) | 12.8, 12.12, 18.1, 18.6 |
| R245 | **Every new file has one owner, three `__init__.py` are this amendment's, and rule 12 says the tagger is never a model call.** Section 13 gains the rows of 18.7 (S1, S2, F5, DS1, DS2, FM1, A1, O4, U1, U3, gate G4 and C1c), DS2's two lexicon files among them (ruling R295), and `data/universe.py` moves from R1a to DS1 (R1a keeps the statistics); `sensors/__init__.py`, `rules/__init__.py` and `features/__init__.py` are created here, docstring-only (R122: `features/` is opened by FM1 in lot 6, before amendment C3, so C3's row is amended); DS2 adds the tagging and cohort calls to DS1's `builder.py` and `loader.py`, S1 adds `SensorAbsentError` and the nested gates to D1's and E1's files, S2 adds `benjamini_hochberg` to E4's, each by the agreement recorded in the map (the R1a and R1d precedent). Rule 12: nothing under `data/`, `cohorts.py`, `rules/` or `sensors/` imports `pmx.gateway` or `pmx.llm`; green on the tree of 2026-09-09 and binding on the first commit that adds a file it covers | 13, 14, 16.6, 18.7 |
| R246 | **The identifier formats of 18.7.** Sensor names, `ru-` rule ids, `hf-` family ids, `co-` cohort ids, the rule author regex, the nine step kinds, the `hn` news code and the facet-value slug, each a constant beside its owning module (R121) | 2, 18.7 |
| R247 | **Decision D-R1: folds are cut by count quantiles of resolution order, 60/20/20 by default, still chronological.** The calendar thirds gave `y2026` 111 train, 46 validation and 130 sealed markets, an inverted pyramid (`docs/REVIEW_2026-09-08.md`). Markets are sorted by `(fold_key_ms, resolved_at_ms, id)` (ruling R290 made the sort key the market's **group** resolution bar, so the cluster rule of R248 is inside the cut instead of a move after it), `k_train = (n * 600) // 1000`, `k_validation = (n * 800) // 1000`, `train_end_ms = fold_key_ms(the market at k_train)` and `validation_end_ms` likewise (a bar open, so a run can clip to it; every market of a group whose key is the cut bar goes to the later fold), the fold predicates of 12.7 keep their form over the new cuts, the thirteen month edges stay for the rolling folds while a continuous instrument follows the headline spans (7.7 and 17.6, amended in place), and the manifest's `split` gains `method`, `quantiles_permille`, the cut dates and the realised counts. `docs/PRD_V2_HARD_OPTIMIZER.md` 6.1's "months 1 to 8 ... 9 and 10 ... 11 and 12" is corrected in place with a 1.1 revision entry: the review's decision was accepted by the user, so the PRD-wins rule of the preamble is honoured by amending the PRD, not by leaving two documents that disagree. `make_folds` (O1) reads the cuts from the manifest, recomputes them from the metas and refuses a mismatch with `FoldIntegrityError` (R248); it never cuts on its own | 7.7, 7.8, 12.7, PRD v2 |
| R248 | **Decision D-R2: folds are cluster-aware and a dataset whose folds split a cluster is refused.** Every market of an `EventCluster` (16.3) and of a Kalshi `event_key` group takes the fold of its **latest-resolving** member, **inside** the cut of R247 rather than by a move after it (ruling R290: a move after the cut is one-way toward the later fold and re-inverts the pyramid D-R1 fixed); a train price path may otherwise encode a sealed outcome that the cross-asset sensor or a cluster feature carries. The manifest's `split.cluster_moves` lists every moved market `(market_id, from_fold, to_fold, group_id)`, the loader recomputes the moves and refuses a mismatch, `pmx data verify` gains the check, and `make_folds`, the rule tester and `claim` refuse a dataset whose folds split a group with `FoldIntegrityError` (13.1). Cohorts do **not** inherit this rule (ruling R293 corrects the wording R266 carried): a cohort has no fold of its own and its markets keep the folds they were cut into | 7.7, 7.8, 12.7, 13.1, 16.3 |
| R249 | **Decision D-R3: a Current events bullet is stamped with the revision time at which it first appeared.** D5's `published_at_ms` for a `wce` item becomes the timestamp of the first revision of `Portal:Current events/<day>` that carries the bullet (`revid` filled, `published_at_source = "revision"`), the end-of-day stamp of 5.5 remaining the fallback when the revision history is unavailable (`published_at_source = "page_day"`) and the blanket lag remaining the floor of `visible_from_ms`; the six-hour figure was a guess and is now a floor over a measured instant. The day key of a news file (7.1) is unchanged in form and now names the revision's day. Applied by DS1, with a rebuild | 5.5, 7.1, 7.3 |
| R250 | **Decision D-R4: the linker's precision is audited and a weak build says so.** Fifty random links per build (`sample_without_replacement` from `dataset.subsample`) are reviewed into `audits/<dataset_hash[:16]>/linker.json` (outside the walk, keyed by the hash, **tracked**, ruling R296 moved it out of the git-ignored dataset tree) with the reviewer's verdicts; the manifest's `news.linker_audit {path, n, precision_permille}` reports it, and a build below `LINKER_PRECISION_MIN_PERMILLE = 800` carries `news_links: "weak"` in `LeaderboardRow.labels` of every row of a run whose roster bought a news sensor. `LeaderboardRow.labels: tuple[str, ...] = ()` is the one carrier of every such label (`news_links:weak`, `taxonomy:weak`, `contamination_audit:coarse`, `window_days:<n>`), filled by `leaderboard.build(..., labels=)` from the manifest by the caller, since the projection reads no dataset. Gate G3 performs the review | 7.6, 7.8, 12.10, 12.11 |
| R251 | **Decision D-R5: the hourly grid is the headline Kalshi grid.** Kalshi's median life is 29 days and it publishes 1-minute candlesticks, so a daily grid discards its intraday content and the latency rule costs a full day; `y2026h` (`interval_min = 60`) is the headline Kalshi dataset, daily stays for Manifold and for the showcase pack, minute grids serve the event studies (18.3). 5.2 and 7.8 say so; one grid per run and one dataset per grid are unchanged | 5.2, 7.8 |
| R252 | **Decision D-R6: the contamination audit is labelled coarse and an LLM result awaits the live book.** The audit of 11.5 detects blatant recall only: every LLM leaderboard row carries `contamination_audit:coarse` in `labels`, and a claim on an LLM genome records its four parts but its `verdict` is `awaiting_live_replication` until `live/` holds at least `LIVE_REPLICATION_MIN_RESOLVED = 100` resolved forecasts of that `genome_hash` and `model` with a positive `skill_lb_micro`; only then may it read `beats_market`. The number is D-R11's and is a default | 11.5, 12.8 |
| R253 | **Decision D-R7: the evolutionary loop is a generator, not a certifier.** 111 training markets cannot detect a Brier edge of 0.005 at a market-level standard deviation near 0.15, and 48 by 30 evaluations make the deflated bound unreachable; 12.6 says in the normative text that the objective **selects** and that certification comes from the sealed fold of a dataset of thousands of markets and from the live book, and a claim's `note` carries the sentence. The per-provider cap stays lifted (a debug option). The targets D-R7 first stated (2 000 and 2 000 at the hourly grid) are restated by R260, R270 and R271 | 12.6 |
| R254 | **Decision D-R9: two-tier fitness, and no genome enters a claim on proxy fitness.** Full engine replay per genome is impossible on hourly and minute grids for a whole population. Tier `proxy`: the belief function evaluated on `pmx.features.matrix` (FM1), precomputed integer feature matrices per `(market, bar)` of the fold, scoring the time-weighted Brier of 12.1 against the market and `pmv_bp` at one bar, with no fills, fees, memory or hive; tier `engine`: `run_generation`'s full replay. Every candidate of a generation is proxy-scored; the elites, the `engine_tier_count` (default `12`, elites always included) best by proxy on train, every archive offer (descriptors need fills) and every claim are engine-scored; `best_validation_lb_micro` and patience read engine scores only. `candidate_scored.tier`, `matrix_hash` and `features_hash` record what an evaluation used, `candidates_evaluated_cum` counts distinct genomes scored on validation at **either** tier, and `claim` refuses (`ClaimRefusedError`) a genome whose store row has no engine-tier validation score. `pmx/features/matrix.py` is FM1's (lot 6) | 9.4, 12.6, 12.11, 13 |
| R255 | **Decision D-R10: the capacity metric.** Kalshi's fee of seven percent of `p(1-p)` and thin books make most micro-edges untradeable, so PnL failure will be liquidity and not skill. `pmx.metrics.capacity.capacity_cents(fills, bars, config, schedule)` (O4) re-prices every fill of a claim run at each scale of `CAPACITY_SCALE_GRID_PERMILLE = (1000, 2000, 5000, 10000, 20000, 50000, 100000)` through `historical`'s cap, slippage and fee (`pmx.engine.liquidity`'s own functions, so rule 9 holds) on the same bars, and reports per market and in aggregate the notional in cents at the **first grid scale** whose after-fee return is at most half the unit-scale return (`-1` when no grid scale halves it, with the grid's ceiling stated). It needs the dataset, so it is computed at claim time and lives in the claim record beside `pnl` (`capacity {per_market, aggregate_cents, halving_scale_permille}`), never in the journal projection | 12.3, 12.8 |
| R256 | **Decision D-R11: prompt mutation is deferred.** O3 (12.9) runs only when the live book holds at least `LIVE_REPLICATION_MIN_RESOLVED = 100` resolved markets: two and a half months of clean markets are not a training set. 12.9 says it in the text; the package text stands | 12.9 |
| R257 | **Decision D-R12: the Manifold separation is a gate check with a structural carrier.** `LeaderboardRow.currency` (`mana` iff `provider == "manifold"`), every 12.12 answer that carries a score carries `currency`, no leaderboard, chart or README sentence pools Manifold with Kalshi, and gates G3 onward check it. Nothing else changes: claims were already per provider | 12.10, 12.11, 12.12 |
| R258 | **Decision D-R13: the universe is an output of the builder, documented in the manifest.** The 731 Kalshi series were picked ad hoc and are category-biased. The builder lists every Kalshi series with at least `BuildConfig.universe_min_settled` settled markets in the window and at least `BuildConfig.universe_min_volume_cents` of volume from the settled walk (defaults `5` and `100_000`, reported against, not laws); `kalshi_series_allow_list` becomes a debug narrowing; the manifest's `universe` block carries the rule, the series with their before and after counts and volumes, and `n_series_before`, `n_series_after`; weather series are kept and carry the builder label `forecastable_from_public_models` in `tags` | 7.4, 7.8 |
| R259 | **Decision D-R14: detectors move before agents.** Seventeen families were scheduled before any inefficiency had been measured. Section 14's rows read lot 5b (DS1, DS2, S1, S2, R2a..R2e, F1..F5, U1, U2) before lot 6 (A1..A6, FM1, O1, O2, O4, L1), the agent roster of 10.5 is ordered by the opportunity map, and `trend` and `revert` stay in the roster as baselines, not as bets. The contract records the order; the plan carries it | 14 |
| R260 | **Decision D-S1, in the form D-S11 and D-S12 corrected it: the build target is stated in cohorts, per venue.** The research dataset must reach `KALSHI_COHORT_TARGET = 40` usable cohorts (`n_train >= COHORT_MIN_TRAIN = 30`) on Kalshi and `MANIFOLD_COHORT_TARGET = 8` on Manifold, whose stated role is breadth and print-tape depth; the market count is whatever that takes (the prototype tagger put Kalshi at about 7 000 markets, review section G) and the 2 000 per venue of D-R7 is a **floor** for Manifold and is superseded for Kalshi by the cohort arithmetic. A build that reaches a market floor and not the cohort floor is a **failed** build: `manifest.build.status = "failed"` with `shortfall` per filter and per venue. **AC-11 of `docs/PRD_V3_TRADING_OPTIMIZER.md` is corrected in place** (it asked for 1 000 markets per venue and said nothing about cohorts) with a 1.1 revision entry; AC-32 supersedes it | 7.4, 12.7, PRD v3 |
| R261 | **Decision D-S2: the interface never reads the demo pack by default.** `GET /datasets` orders `purpose: "research"` datasets first, the API's default dataset is the newest sealed research dataset, the market index is server-side paged, and a showcase dataset is reachable only through an explicit selector that labels it `showcase`. U1 and U2, lot 5b | 12.12 |
| R262 | **Decision D-S3: `window_days` is explicit, 365 by default and refused above 730.** `WINDOW_DAYS_MAX = 730`; `BuildConfig.__post_init__` raises `InvalidConfigError` above it, and the two reasons are in 5.6's normative text so no flag widens it silently: a resolution older than a model's knowledge cutoff is a possible recall rather than a forecast, and a regime three years old is not the regime being traded. The manifest records `window_days` and `resolution_span {min_ms, max_ms}`; a row from a dataset with `window_days > 365` carries `window_days:<n>` in `labels` | 5.6, 7.4, 7.8, 12.10 |
| R263 | **Decision D-S4: `purpose` replaces `Dataset.is_demo_pack`, and a showcase dataset is refused by name.** `DatasetManifest.purpose: "research" | "showcase"` (absent in a manifest written before this amendment: `showcase` iff `sealed == false and providers == ("demo",)`, the old signature, else `research`; the builder writes it always from DS1 on). A showcase dataset is exempt from the window rule of 5.6, seals and replays like any other, may be run by `run_backtest`, and is **never** the source of a fold, a fitness value, a rule promotion, an insight or a claim: `make_folds` (O1), `run_generation` and `evolve` (O2), `claim` (O4), the rule tester (S2) and `pmx.features.matrix` (FM1) each raise `ShowcaseDatasetError` (13.1) before reading a market, and each has a test. No silent skip anywhere. `is_demo_pack` is deleted by DS1 in the same commit; 7.1's exemption paragraph reads `purpose` | 5.6, 7.1, 7.8, 12.7, 13.1 |
| R264 | **Decision D-S5: the showcase pack grows past twelve.** DS2 builds it (`pmx.data.showcase`) from landmark events wherever a real tape survives in Wayback or Manifold's history, with the same bars, trades, news and as-of stamps as a research market, `purpose: "showcase"`, sealed, a few dozen markets, and a `notes` entry documenting what could not be sourced. The v1 demo pack stays as the migration identity of 7.10 and is not the showcase pack | 7.1 |
| R265 | **Decision D-S6: a controlled vocabulary, three facets, and `provider_labels`.** 7.14 is written: `tags.v1.json` with the `subject` (one or more, tagger precedence order, at most 4), `structure` (exactly one) and `horizon` (exactly one, derived from `close_at_ms - created_at_ms`, never from provider text and never from `resolved_at_ms`) facets and a `builder` label list; `tags` stays as the sorted union of a market's facet values and labels; the raw provider strings move to `provider_labels`; the four fields are optional in `market.v2.json` (a file written before the taxonomy loads) and required by the loader on a dataset whose manifest carries the `taxonomy` block; `market_listed` gains the four, optional until R274's lot | 7.2, 7.14, 9.2 |
| R266 | **Decision D-S7: the cohort is a first-class object and the unit of comparative analysis.** `Cohort(cohort_id, category, subject, structure, horizon, provider, n_train, n_validation, n_sealed, usable, usable_for_paired_test)` keyed on the primary subject, listed by the builder into `manifest.cohorts` and by the loader into `Dataset.cohorts` through the one `pmx.cohorts.list_cohorts`, usable at `n_train >= 30`, `usable_for_paired_test` false when any fold is empty (D-S13), and **never a unit that moves a market between folds** (ruling R293 replaces this ruling's "never crossing a fold", which read as the cluster rule of R248 and would have collapsed the train fold onto the sealed one; `FoldIntegrityError` on a count mismatch); `MarketMeta` gains `subject`, `structure`, `horizon`, `provider_labels` and `cohort_id`; R2d runs per cohort, `calibrator`'s ledger keys on the cohort, `RuleScope.cohorts` names them and a family may be keyed on one, `LeaderboardRow.cohort_id` gives one row per usable cohort, a claim gains `per_cohort` rows with their own `K` and verdict at the same `CLAIM_MIN_MARKETS`, one per cohort of the dataset, and there is **no** `pmx claim --cohort` (ruling R283: a per-cohort claim would be a second sealed read under a `claim_id` naming no cohort; `CohortRefusedError` moves to `pmx.cohorts.cohort_or_refuse`, the per-cohort leaderboard and the `comparative` detector). A `platform-meta` market belongs to no cohort | 7.2, 12.3, 12.6, 12.7, 12.10, 12.11, 13.1, 18.5 |
| R267 | **Decision D-S8: the tagger is deterministic and auditable, never a model call.** The sealed series-to-facets map first, then the vocabulary's keyword and pattern rules over the question, then a counted `other`; no network, no wall clock, no randomness; the two lexicon files are copied into `taxonomy/` inside the walk so they enter `dataset_hash`; byte-identical across two runs is a test; rule 12 (R245) binds the import graph; and `tests/test_taxonomy.py` poisons 7.9's fields and asserts the facets do not move | 7.14, 18.7 |
| R268 | **Decision D-S9, in the form D-S14 corrected it: coverage is measured per venue and labelled at ninety percent.** The manifest's `taxonomy` block records per venue and per facet the coverage, the distinct values, the `other` and `platform-meta` counts, the cohort size histogram, the cohort counts and a label; a venue below `TAXONOMY_COVERAGE_MIN_PERMILLE = 900` on `subject`, or with fewer than `TAXONOMY_MIN_USABLE_COHORTS = 10` usable cohorts, is `taxonomy: "weak"` **for that venue only** (a single 95 percent bar is unreachable on Manifold by construction), carried in `labels` on every row and chart that groups by facet or cohort; the fifty-tagging audit is stored at `audits/<dataset_hash[:16]>/taxonomy.json`, **tracked** (ruling R296), with its precision in the manifest, reviewed by gate G3 | 7.8, 7.14, 12.10 |
| R269 | **Decision D-S10: the market view is a browsable index.** `GET /datasets/{name}/markets` gains filters on `category`, `subject`, `structure`, `horizon`, `provider`, `fold`, `hardness_tag` and `outcome` and sorts on `resolved_at_ms`, `life_days`, `volume_milli_total` and `final_price_bp` (the last two after the cursor passes resolution, 14's U2 rule), `GET /datasets/{name}/cohorts` lists the cohorts and `GET /datasets/{name}/cohorts/{cohort_id}` the markets of one with each agent's calibration on it; U2 and U3 build the views and U5's tour gains the chapter | 12.12 |
| R270 | **Decision D-S11: the cohort target differs per venue.** Kalshi carries the comparison at `40`; Manifold reached zero cohorts of ten on the prototype and has no dense templates to concentrate, so its target is `8` and a gate that finds it below records the shortfall and does not fail the build, while a gate that finds Kalshi below `40` fails it. Stated in 7.4 beside R260 | 7.4, 12.7 |
| R271 | **Decision D-S12: the market floor follows the cohort target and the fallback is decided in advance.** Forty Kalshi cohorts at `n_train >= 30` imply on the order of 7 000 markets (review section G) against a reachable in-window listing of about 15 000 rows living a week or more (`docs/BUILD_STATE.md` 7.5), so DS1 reports the reachable count against the target before building, and when the 365-day window cannot deliver it the order is: **first** widen `window_days` toward `WINDOW_DAYS_MAX`, **then** relax `min_trades` (and `min_traded_bars`) with the count removed stated per filter, and **only last** lower the cohort target, with the reason recorded in `manifest.build.fallbacks`. Widening the window costs contamination risk for LLM agents alone, which the clean-market rule handles; lowering the cohort target costs the comparison, which nothing recovers | 7.4 |
| R272 | **Decision D-S13: no cohort is measured before the fold fix lands.** All six cohorts that reached ten markets on the prototype sat inside one fold, a consequence of the inverted split; DS2 starts after DS1's rebuild with R247's and R248's folds, and the loader reports per cohort its per-fold counts and `usable_for_paired_test`, false when any fold is empty. Section 14's DS2 row says "after DS1" | 7.7, 12.7, 14, 18.5 |
| R273 | **Decision D-S14: the vocabulary starts from the measured rules, and `platform-meta` is a subject.** 7.14's tables carry at least the structure values and subject values the prototype measured (`threshold-above` 145, `threshold-below` 15, `count-over-period` 10, `head-to-head` 9, `range-band` 7, `by-date` 7 and 12; the seventeen subjects), `platform-meta` names Manifold's self-referential markets (7 measured, against 8 `nonpredictive` provider labels, not the same set, reconciled by the tagger) and keeps them out of forecast cohorts, and the coverage bar is R268's per-venue ninety percent. AC-32 and AC-34 are read in their restated form | 7.14, 18.5 |
| R274 | **Gate G2's four declared-not-applied shapes are restated where they belong and applied together by the first engine lot after this amendment.** R213's `Execution.__init__(..., t0_ms, t1_ms)` and the last-bar drain of a queued item whose instrument has no later bar as `order_rejected(not_tradable)` (8.6, 16.2, 17.2), R214's `quote_bar(..., bar_prev=)` (16.1), R217's continuous calibration entries through `continuous_entry` (12.2), R221's `PerMarket.n_quantile_forecasts` and `RunProjection.seed` (12.11), together with this amendment's `observation_built.sensors`, `run_started.sensor_catalogue_hash`, `RunConfig.sensor_catalogue_hash` and the four `market_listed` facets (R231, R265): one lot, one commit, E2 and E5 with D7's dataclasses, **the contract fixture and every pinned hash regenerated in that same change** (the backtest fixture completed as R202 did, the pinned config hashes of `tests/test_runner.py` moved beside today's), `tests/test_runner.py::test_every_queued_item_produces_exactly_one_execute_phase_event` reading `dropped == 0` where it pins `dropped > 0` today, and `ENGINE_VERSION` and `CONTRACT_VERSION` bumped in that commit as R111 and R227 require, because from that commit a run exists whose bytes a later engine is expected to reproduce. Until then each shape stays declared in its section and in `journal.v2.json` as optional | 8.6, 9.2, 12.2, 12.11, 13.2, 16.1, 16.2 |
| R275 | **What this amendment leaves alone.** `ENGINE_VERSION` stays `2.0.0` and `CONTRACT_VERSION` stays `"2.0"`: no ruling here changes a byte of a journal a run has written, because no such run exists (R227's trigger, unchanged in 13.2). `run_id` not naming the population (BUILD_STATE 8.7) is not settled: neither review assigns it and it belongs to R274's lot with the bump. R1a's universe statistics, R1b's matcher, the detectors' bodies, O3's package text and every family rule of 10.5 not named above stand as written. The numbering of this section starts at R230 because R228 and R229 are gate G2's audit rulings | 13.2, 15.3 |
| R276 | **The live record and the transfer test are as-of, not fold-bounded and not unbounded** (finding C1). 18.2 step 7 said `live_support` and `live_interval` cover "the rows after `fit_t1_ms` only", with no upper bound, so a rule promoted on the rolling pair at `k` carried a record computed over months `k + 2` to 12: an agent trading month `k + 2` saw an insight demoted by what the validation months did, which is the field 7.9 already forbids ("a rule's live record beyond `now_ms`"). The record is therefore **as-of**: at a bar `b` it covers the matched rows with `fit_t1_ms + interval_ms <= t < b`, the tester recomputes it at each generation close with `b` the generation's last completed bar and L1 daily over `live/`, and what reaches a view at `now_ms` is the value last stamped at or before it. Step 8's transfer test reads the promotion's own replicate fold, restricted to the targets outside the scope, and no bar at or after `fit_t1_ms + interval_ms`. **Against the proposal** to freeze the window at `replicate_end_bound`: a record that never grows can never demote a rule that decays, which is the one job the live record has. The sealed half of the finding does not hold: 18.2's opening already bars the tester from the sealed fold (rule 3), so the leak the finding traced ran through validation, not through sealed | 7.9, 10.4, 18.2 |
| R277 | **`Folds.rolling` is clipped to the training fold and `k` is an argument, not an inference** (finding C2). 12.7 declared the six pairs `(months 1..k, month k+1)` for `k` in `4..9` over 7.7's thirteen month edges and nothing intersected them with `train_end_ms`, while 18.2 step 5 gave a second reading ("`k` the last complete month of the training fold") that need not lie in `4..9`. Under R247's count quantiles the calendar position of `train_end_ms` is data-dependent, so on a front-loaded distribution the unclipped set replicated rules on validation and sealed months. `Folds.rolling` holds the pairs for the `k` in `4..9` whose month `k + 1` ends at or before `train_end_ms`, ascending, possibly fewer than six; `pmx rules test --rolling k` takes `k` from that tuple and the evolution uses the largest; `make_folds` raises `FoldIntegrityError` when the tuple would be empty, whose remedy is 7.4's fallback order and not a silent narrower test. O1's test asserts no rolling replicate month holds a validation or sealed market | 7.7, 12.7, 13.1, 18.2 |
| R278 | **`SensorInputs`, `run_workflow` and `StepTrace` are declared in 12.11** (finding C3). `SensorInputs` occurred once in the whole document and was defined nowhere, while S1 (fifteen `sense` bodies), E1 (the observe phase) and FM1 (the proxy matrix, with no observation in sight) all build against it; `run_workflow` had prose and no signature, while 9.3 makes the runner the one emitter of `workflow_step_executed` with three per-step numbers it can get from nowhere else. 12.11 now declares `SensorInputs` field by field (the meta, the completed bars, the last bar's quotes, the prints, the visible news **by source**, the applied cash events, the agent's own hive and memory views, the peer instruments' bars, the granted research payloads), `run_workflow(workflow, *, genome, obs, blocks, memory, rng) -> tuple[Actions, tuple[StepTrace, ...]]` and `StepTrace(step_index, kind, ref, n_inputs, n_out, output_sha256)`, which is exactly 9.2's row | 9.2, 12.11, 18.1, 18.4 |
| R279 | **`fires` reads the blocks it is handed, `readable_by` is the filter, and a diet cannot be moved by a rule it cannot read** (finding C4). 18.2 said `fires` "reads the sensor blocks of that bar" without saying whose, and 18.1 makes an unbought field raise `SensorAbsentError`, so a rule promoted on `hn_story_points` either crashed a diet without `hn` or silently did not fire, with nothing choosing. `fires` is total and never raises; `Rule.readable_by(sensors)` is the predicate the hive view and the `rules` step apply first; the runner fills `Hive.view(..., blocks=)` from the agent's own sensed observation, so an agent sees only the insights its diet can read, which is the subtraction rule of 18.1 applied to knowledge; the tester always evaluates against the whole catalogue, so a ledger interval is one full-diet statement; and `InsightView` carries `required_sensors` so a reader can see what a diet cannot read | 10.4, 18.2, 18.4 |
| R280 | **The rule shift reads `claim.direction` and refuses a `volatility` claim** (finding C5). 10.5, 18.4 and R240 all spelled the shift as `lift_bp * weight_permille // 1_000`, and `lift_bp` is the interval's `point` over `y_row`, every row of which is **already multiplied by `direction`**; since promotion requires `interval.lower > 0`, a promoted "the price is too high" rule raised the agent's probability, and an unsigned `volatility` excess was added to a price. The shift is `sum(claim.direction * (lift_bp * weight_permille // 1_000))` over the firing insights whose `claim.kind` is `bias` or `drift`; a `volatility` insight enters no belief and is available to a `sizing` step only. The direction multiplies the rounded magnitude, so a down-rule and its mirror shift by equal amounts, which integer floor division of a negative product would not give. A1's test asserts a promoted `direction = -1` bias rule lowers `rule_follower`'s `prob_ppm` | 10.5, 18.2, 18.4 |
| R281 | **Proposing a rule is affordable, its refusal is named once, and the allowance reaches the runner** (finding C6). `SENSOR_BUDGET_UNITS_DEFAULT` was the catalogue's own `17` while a proposing bar required `diet_cost_units + 1 <= allowance`, so every one of the eight v1 archetypes, which carry the full diet by 18.1, was permanently barred from proposing and one of PRD v5's three authors never fired. `RULE_PROPOSAL_COST_UNITS = 1` and `SENSOR_BUDGET_UNITS_DEFAULT = sum(cost_units) + RULE_PROPOSAL_COST_UNITS = 18`; a proposal that the allowance cannot pay for is `action_rejected(scope="rule", reason="budget_exceeded")` (8.4, an existing `RejectReason`) and the genome keeps running; `RunConfig` gains `sensor_budget_units` and `sensor_budget_by_agent` in the shape `research_budget_by_agent` has, because the runner applies a per-bar cap and had no field carrying it; and "the genome does not run" becomes `run_backtest` raising `InvalidConfigError`, since the cull is O2's at generation close and a runner that drops an agent silently loses a row | 8.1, 8.4, 18.1, 18.2 |
| R282 | **The rule path gets its own null, with the `(b + 1) / (B + 1)` estimator and a permutation count that follows the family** (findings C7 and C19). Reusing `permutation_null` was unbuildable and wrong: its `market_prices`, `outcomes` and `bar_weights_ms` arguments have no meaning for a rule's matched `(market, bar)` rows, and it tests a Brier skill against the market while promotion tests the mean of `y_row`, so a rule with the right direction and a `magnitude_bp` off by half, which 18.2 calls useful, failed one gate and passed the other. 12.4 gains `rule_permutation_p_ppm(y_rows, fired, blocks, *, rng, permutations)`, which permutes the firing labels within each block and returns `round_half_up(PPM_ONE * (b + 1), permutations + 1)` on the promotion's own statistic; `permutations = min(RULE_PERMUTATIONS_MAX = 20_000, max(RULE_PERMUTATIONS_MIN = 200, 20 * n_screened))`; a family whose `n_screened` exceeds `1_000` is `RuleRefusedError(reason="family_too_large")` and must be split by template. The shuffles draw from `stats.permutation` and the effect's bootstrap from `stats.bootstrap`, the registered substreams of 6.3: 18.2 had named `rules.permutation` and `rules.bootstrap`, which are in no `SUBSTREAMS` list, and 6.3 says adding a name means adding it to `pmx.rng` in the same commit; these two shuffles run inside `pmx.metrics.stats`, where the two registered names already live, so nothing is added. **Against the proposal** to redefine `permutation_null`'s `p_value_ppm` for every caller: the claim path reports that number beside a Bonferroni-deflated bound and part 4 of the four-part bar thresholds `null_lb_micro` and never the p-value, so its resolution decides nothing there, and moving an implemented E4 function would move numbers gate G2 measured. The finding's arithmetic is corrected in passing: once enough rules report `p = 0`, `k` does climb past ten and non-zero p-values are rejected, so the failure is the inadmissible `p = 0` and the coarse grid, not a hard floor at `k = 10` | 12.4, 13.1, 18.2 |
| R283 | **There is no per-cohort claim: one claim, one sealed read, one row per cohort** (finding C8). `pmx claim --cohort`, `POST /claims`'s `cohort_id` and `access.jsonl`'s `cohort_id` existed while `claim_id` named no cohort, so two cohort claims on one genome collided on one filename and the second was refused as an aborted peek. **Against the proposal** to extend `claim_id` with a cohort segment: a per-cohort sealed read is a second bite at the same sealed markets, and a genome that may claim each cohort separately can cherry-pick the one that cleared, which is exactly what PRD 2.6's ledger exists to prevent. The flag, the body field and the ledger field are deleted; the whole-dataset claim's `per_cohort` rows are the cohort statement, each with its own `K` per `(dataset_hash, cohort_id)` and its own verdict, and a cohort that is not `usable_for_paired_test` carries its counts, no bounds and `verdict: "not_usable"`. `CohortRefusedError` moves to `pmx.cohorts.cohort_or_refuse`, the per-cohort leaderboard and the `comparative` detector | 12.8, 12.10, 12.12, 13.1, 18.5 |
| R284 | **`family_id` names the data the family was drawn on, and every ledger row names its fold pair** (finding C9). Keyed on `[generation, template]` alone, `pmx rules test --rolling 4`, `--rolling 5` and `--headline` on one dataset registered three families under one id with three payloads, the pre-registration guard was satisfied by the wrong registration, and the duplicate rule of step 4, defined on `(dataset_hash, fit, replicate)`, had no row carrying its key. `family_id = "hf-" + sha256(canonical_json([dataset_hash, generation, fit_fold, replicate_fold, registered_at_ms, fit_t1_ms, template]))[:16]`, `HypothesisFamily` gains `dataset_hash`, `fit_fold` and `replicate_fold`, and every `families.jsonl` and `rules.jsonl` line carries the three. All of it is derived from the data, so determinism is untouched | 18.2, 18.7 |
| R285 | **The sentinel is a field of the catalogue, not a sentence in a description** (finding C10). "The value the feature's `description` names, `lo` unless the description says otherwise (a signed gap reads `0`)" contradicted itself, and applied literally to the shipped fixture it made `ret_7b_bp`, `ret_30b_bp`, `ret_90b_bp`, `mid_minus_last_bp` and `volume_milli_z_milli_30b` read minus one hundred percent over the opening bars of every market, which is a constant the miner would find and promote. `SensorFeatureSpec` gains `sentinel: int`, `sensor.v1.json` requires it, the fixture fills all seventy-five and `CATALOGUE_HASH` is regenerated in the same edit. The filling rule, which S1's test asserts: a signed quantity's sentinel is `0`, a `minutes_since_*`, `bars_since_*`, `bars_to_*` or `*_days_since_*` count's is its `hi`, everything else takes its `lo`; `lo <= sentinel <= hi` always, and no signed feature's sentinel is its `lo` | 18.1, `sensor.v1.json`, `sensor.catalogue.json` |
| R286 | **The `SensorBlock.market_id` comment was wrong, and the fixture was right** (finding C11). One code block named three different sets of observation-level sensors: the `market_id` comment said "memory, the hive", the `per_market` comment said "hive_reputation", and the fixture ships `per_market: true` for `memory` and `hive_insights`. **Against the proposal** to move `memory`'s features or to flip the fixture: one block per open market with the observation-level values repeated is what a rule evaluated per `(market, bar)` needs, `hive_insights`'s features are per market by construction, and the fixture agrees with the `per_market` comment already, so the defect is one comment. `market_id` is `None` exactly when `spec.per_market` is `False`, which on the shipped catalogue is `hive_reputation` and nothing else, and `CATALOGUE_HASH` does not move for this | 18.1 |
| R287 | **A sensor's `granularity_ms` and `lag_ms` are derived maxima over its sources** (finding C12). The two fields were singular while `sources` is plural, and the shipped `macro_releases` advertised a one-second, zero-lag sensor half of whose items (`cboe`) are day-stamped and six hours late, so the column a reader consults to ask whether a sensor can leak was false on the one row where it mattered. `granularity_ms = max(SOURCE_GRANULARITY_MS[s] for s in sources)` and `lag_ms = max(SAFETY_LAG_MS_BY_SOURCE[s] for s in sources)`, `0` without a source; S1 asserts the identity, the fixture carries the derived values (`macro_releases` reads a day and six hours, `CATALOGUE_HASH` regenerated), and the builder goes on stamping each item with its own source's lag, so nothing is slowed down. A sensor whose sources are partly inadmissible on a grid keeps the admissible ones, `manifest.news.sources` reports the dropped ones, and the derived pair is recomputed over what the dataset carries | 18.1, 18.3, `sensor.catalogue.json` |
| R288 | **`market_listed` carries `cohort_id`** (finding C13). `PerMarket.cohort_id` said it is read off `market_listed` once R274's lot journals the facets, and `cohort_id` was not one of the four facets that lot adds; since the projection rebuilds `results.json` from `journal.jsonl` alone (9.5), E5 would have shipped a second implementation of `pmx.cohorts.list_cohorts`'s keying rule, `platform-meta` and `other` exclusions included, for a key a claim's `per_cohort` rows and a leaderboard slice are grouped by. `market_listed` gains `cohort_id: str | null` (optional in `journal.v2.json` until R274's lot, the projection reading `null`), 7.14 reads "the four and `cohort_id`", and 18.8's deferral row names it | 7.14, 9.2, 12.11, 18.5, 18.8 |
| R289 | **`diet_class` is computed from `observation_built.sensors`, and a pre-C1c journal reads the full catalogue** (finding C14). The descriptor was "a pure function of `Genome.sensors`" and the projection that fills `Descriptors` may read nothing but the journal, which carries no genome, so AC-3's replay guarantee or the fourth archive axis was broken. The projection reads the agent's first `observation_built.sensors` of the run, equal to `Genome.sensors` by construction. **Against the proposal** to add a `diet_class_known: false` flag: a journal written before R274's lot is a full-catalogue run by construction (the runner passed `None` to every agent), so the projection reads `SENSOR_NAMES` and the descriptor is `2`, which is true rather than unknown, and no fourth state enters an archive axis with three bins | 9.5, 12.5, 18.1, 18.8 |
| R290 | **The cluster rule is inside the count-quantile cut, and `build.status` is per venue** (finding C15). Cutting on the market's own resolution and then moving each cluster and `event_key` group to its latest member's fold moves markets **one way only**, always later and without bound, thinning the train fold exactly on the dense Kalshi groups the cohort target is built from: R247's own inverted pyramid, reintroduced silently. The cut key becomes `fold_key_ms(m)`, the resolution bar of the latest member of the market's group, and the quantiles are cut on `(fold_key_ms, resolved_at_ms, id)`, so the folds R248 intended are reached in one step, the 60/20/20 shares hold up to the ties of one bar and no move follows; `split.cluster_moves` keeps its shape and reports the markets whose own bar sits in an earlier fold, and the manifest gains `split.realised_permille`. **Against the proposal** of a `FOLD_TRAIN_MIN_PERMILLE` refusal: a floor with no recourse turns a real dataset into a dead one, while a group-aware cut removes the drift by construction; `make_folds` refuses only what cannot be used, an empty fold. Separately, 7.4's blanket "a build that misses the cohort floor is failed" contradicted R270: `status` is `"failed"` on a Kalshi shortfall and `"ok"` with `build.shortfall.manifold` on a Manifold-only one | 7.4, 7.7, 7.8, 12.7, 13.1 |
| R291 | **The showcase quarantine covers the memory and hive carry-forward** (finding C16). 5.6 listed six refusals and none of them bound `memory_from_run_id` or `hive_from_run_id`, whose only guard is `t1_ms <= t0_ms`; a showcase pack holds events resolved years ago, so that guard passes by construction and a landmark event could seed a research run's `calibrator` bin table and its hive resolutions, through a channel 8.1 itself calls a channel into an observation. `run_backtest` raises `ShowcaseDatasetError` when the named run ran on a showcase dataset and `LeakError` when its `dataset_hash` differs from this run's. **Against the proposal's `--allow-cross-dataset-memory` escape hatch**: a flag that "no claim path may pass" is the kind of flag that ends up passed; memory travels forward inside one dataset, and a live run seeded from a backtest is a mechanism the live wave must write down rather than a flag | 5.6, 8.1, 13.1 |
| R292 | **The capacity metric has a formula** (finding C17). "The notional at the first grid scale whose after-fee return is at most half the unit-scale return" left the denominator unnamed, evaluated the unit scale against itself and said nothing about the aggregate. `notional_cents(s)` is the sum of `abs(cash_delta_cents)` over the fills re-priced at `s`, `ret_bp(s) = bp_ratio(pnl_after_fees_cents(s), notional_cents(s))`, and the metric has three states: `ret_bp(1000) <= 0` gives `capacity_cents = 0` and `halving_scale_permille = 0`; otherwise the smallest `s > 1000` with `ret_bp(s) * 2 <= ret_bp(1000)` gives `capacity_cents = notional_cents(s_prev)`, the largest tested notional that kept more than half; no such `s` gives `-1` with `grid_max_permille`. The aggregate is computed on the aggregate curve. **Beyond the proposal**: the capacity is the notional at the scale **below** the halving scale, not at it, because a size the edge did not survive is not a capacity. The finding's third sub-claim does not hold and is refuted: on a negative unit return the old wording did not return `-1`, it was satisfied at scale 1000 and reported the unit notional as the capacity, which is worse | 12.3 |
| R293 | **A cohort is not a unit that moves a market between folds** (finding C18). "**A cohort never crosses a fold**" sat one paragraph from R248's rule that a cluster group really is moved into one fold, and contradicted the three per-fold counts in the same dataclass: on the cluster reading, every market of a dense Kalshi series would be pulled into one fold and the paired test the cohort exists for would be destroyed. The sentence is replaced by what was meant: a cohort has no fold of its own, each of its markets keeps the fold 7.7 gave it, `n_train`, `n_validation` and `n_sealed` are what those folds left, and a zero in any of the three is `usable_for_paired_test = false`. R248's and R266's wording is corrected in place | 7.7, 12.7, 18.5 |
| R294 | **Architecture rule 8 binds `analysis/` and not `pmx.rules`, and `rule_proposed` keeps one writer** (finding C20). 18.2 said rules 3 and 8 apply to `pmx.rules` exactly as to `pmx.analysis` while 9.3 makes `rules/tester.py` the one emitter of four journal events, so S2 would have refused to import `pmx.journal` and O2 would have handed it a `Journal`. Rule 3 binds the tester (it reads no sealed fold) and rule 8 does not: the tester writes no **backtest** journal and does write its four events into the evolution journal and its ledger. `tests/test_architecture.py` keeps scanning `analysis/` alone, which is now what the text says. The tester also stops appending `rule_proposed` lines: that event has one emitter, `engine/runner.py`, and `pmx rules ledger` copies its rows out of the run journals | 9.3, 16.6, 18.2 |
| R295 | **DS2's two lexicon files are section 13 rows, and the two series maps are two vocabularies** (finding C21). 18.7 listed `tags.v1.json` and `kalshi_series_facets.v1.json` and asserted section 13 carries one owner per new file, while section 13's lexicons block listed neither, so two packages could have edited a series map. Both rows are added with DS2 as the owner. `kalshi_series_facets.v1.json` (the tagger's series-to-facets map, 7.14) and D2's `kalshi_series_subjects.v1.json` (the linker's series-to-subjects map, 7.6) are different vocabularies with different purposes; the former never supersedes the latter, and DS2 derives it from the latter where the two agree and records the derivation in the file | 7.14, 13, 18.7 |
| R296 | **The two human audits live in a tracked `audits/` tree** (finding C22). R250's linker audit and R268's fifty-tagging audit were written under `data/datasets/<name>/audit/`, which section 13 marks generated and git-ignored, while `claims/` and `rules/` were made tracked for exactly this reason: a reviewer's fifty verdicts cannot be regenerated and are the sole evidence behind a label gate G3 reads. **Against the proposal's alternative** of carving an exception into the ignore rule: a re-inclusion under an excluded directory is not expressible in git, so the files move to `audits/<dataset_hash[:16]>/linker.json` and `audits/<dataset_hash[:16]>/taxonomy.json`, a top-level tree the ignore file never mentions and therefore tracks with no change to it. Still outside every dataset hash, still keyed by the hash they audit; `dataset.v1.json`'s audit-path pattern follows | 7.1, 7.6, 7.14, 9.5, 13, `dataset.v1.json` |
| R297 | **AC-6 is forty percent of the reachable cells** (finding C23). The diet axis trebled the archive to 144 cells and AC-6's absolute target from 20 to 58, on an axis that is degenerate at generation 0 because all eight v1 archetypes carry the full diet and therefore sit in `d2`; every other target in this amendment was corrected downward by measurement, and this one moved upward by arithmetic. `ARCHIVE_CELLS_REACHABLE = 48 * (the distinct diet_class values among the genomes scored at the engine tier)`, AC-6 is forty percent of that, and both numbers are reported: 20 cells while one class is populated, 58 once three are. **Against the proposal's alternative** of giving `DEFAULT_ROSTER` a spread of diets: that changes what the eight archetypes see, breaks the byte-identity promise of section 18's opening ("nothing already built is invalidated") and buys a target with a behaviour change nobody measured | 12.5, 14.1, 18.1 |
| R298 | **A minute build has a field for its list, and AC-26's sensor sets are four named ones** (finding C24). 18.3 required "an explicit instrument or series list" while `BuildConfig` carried no instrument list and R258 had demoted `kalshi_series_allow_list` to a debug narrowing. `BuildConfig` gains `instruments: tuple[str, ...] = ()`, `__post_init__` refuses `interval_min == 1` with both it and the allow-list empty, and on a minute build the allow-list **is** an input, the one exception to R258's rule, because a minute build has no universe walk to derive a list from. Separately, 7.9's poisoned-future test "for every sensor set" is two to the fourteenth sets with `tape` mandatory: `SENSOR_SETS_UNDER_TEST` is the four sets `("tape",)`, tape plus every market sensor, tape plus every news sensor, and `SENSOR_NAMES`, a constant beside E1's test | 7.4, 7.9, 18.3 |
| R299 | **A `torch_policy` genome's diet covers its own vector.** The amendment flagged this itself and the critic passed over it: `features.v1` is unchanged and a torch policy is fed the thirty-seven-wide vector whatever the diet, so an unbought sensor's fields arrive at their sentinels and silently change the policy's input distribution by diet. `torch_policy`'s `FamilySpec.required_sensors` is every sensor carrying at least one `features_v1_index` (`tape`, `calendar`, `microstructure`, `volume_profile`, `cross_asset`, `wiki_daily`), and `genome_from_dict` and `mutate` refuse a torch genome that omits one. A learned policy scored on a distribution its training never saw is a broken input, not a diet experiment, and nothing downstream can tell the two apart | 16.5, 18.1 |
| R300 | **A proposer cannot flood a family.** The amendment's second open question: `rule_id` is content-addressed and a rejected rule is a duplicate, so an agent could dodge the duplicate by perturbing a threshold by one unit, while `RULE_MINER_CANDIDATES_MAX` bounds the miner alone. `RULE_PROPOSALS_PER_GENERATION_MAX = 20` per agent bounds the other authors (the excess is `action_rejected(scope="rule", reason="budget_exceeded")`), a perturbed rule still counts in `n_candidates` and still enters the family's `m`, and R282's `family_too_large` refusal caps what a family may submit at all. Both numbers are defaults the first evolution with rules reports against | 18.2 |
| R301 | **A cohort row is read under the vocabulary it was cut under, and that version already exists.** The amendment's sixth open question: a reorder of `tags.vN` moves every `cohort_id`, and nothing said a claim's `per_cohort` rows name the lexicon version they were cut under. They do now, as `lexicon_version` copied from `manifest.taxonomy.version`; no field is added to `Cohort` or to the manifest, because the version is already there once and a second copy is a second thing to keep true. The `horizon` boundaries and the tagger's precedence order are part of that version: moving either is a new lexicon version and therefore a new dataset hash, never an edit in place | 7.8, 18.5 |
| R302 | **What this arbitration leaves alone.** The `(declared, <applier>)` convention of 9.2 and 9.4 stands: the critic did not object, `tests/test_contract_schemas.py` reads the marker, and a second table with its own header would split one catalogue in two. The amendment's second open question is answered by R277: with the rolling pairs clipped to `train_end_ms`, a rule promoted at `k` is visible from `fit_t1_ms + interval_ms`, which is strictly after every bar its promotion read, whether month `k + 2` falls inside the training fold or past it, so no leak survives the clip. `ENGINE_VERSION` stays `2.0.0` and `CONTRACT_VERSION` stays `"2.0"` for R275's reason, unchanged by anything here: no run exists whose journal bytes any of these rulings moves, the fixtures this pass regenerated are contract documents and not run artefacts, and R274's lot still carries the first bump | 9.2, 9.4, 13.2, 18.2 |

Amendment C1c's own review is **closed**: one critic raised twenty-four findings (eight blockers, twelve
major, four minor), every one was verified in the text, twenty-three were upheld in whole or in part and
fixed in place, three of those had their reasoning corrected, and the one sub-claim that did not hold is
refuted in R292. Nine were resolved against the fix the critic proposed, and four rulings answer questions
the amendment flagged about itself. What is left is code, listed in 18.8 with the package that applies
it.

---

## 16. v3 interfaces (amendment C1)

`docs/PRD_V3_TRADING_OPTIMIZER.md` adds market realism at scale, opportunity detection, learned agents,
an adversarial market maker and portfolio construction; `docs/PLAN_V3_WAVES.md` builds them in waves 7 to
11. This section is the amendment those waves are written against, and it lands **before** part 1's wave
2 so that E2 and E5 are built once: the execution model goes behind a protocol now, the decision latency
rule goes into the phase order now, and the objects the later waves exchange are declared here rather
than negotiated later. Everything below binds exactly as sections 1 to 14 do. Where it replaces earlier
text, the earlier text has already been amended in place and the change is a ruling in 15.8.

### 16.1 The `LiquidityModel` protocol and the envelope rule

`pmx.engine.liquidity` (E2) is the one module in the repository that computes a fill price (ruling R113,
architecture rule 9 of `tests/test_architecture.py`). `Execution` no longer prices anything: it validates,
nets, truncates against cash and journals, and asks the run's model what a fill costs.

```python
# pmx.engine.liquidity (E2). Bar and FeeSchedule are sections 7.2 and 8.8; Protocol is typing.Protocol.
MILLI = 1_000                                # milli-contracts per contract, the unit of bar.volume_milli
LIQUIDITY_MODELS = ("historical", "calibrated_impact", "adversarial_mm")

@dataclass(frozen=True, slots=True)
class LiquidityMarketView:                   # everything a model may see of a market, and nothing else
    market_id: str; provider: str; category: str; currency: str
    fee_schedule_id: str; source: str        # "api" | "reconstructed" (section 7.2)
    interval_min: int
    liquidity_decile: int                    # 0..9, ranked on the TRAINING fold only (ruling R135);
                                             # -1 when the manifest carries no impact block
    kind: str = "binary"                     # amendment C1b, 17.1: one of INSTRUMENT_KINDS
    tick_size_micro: int = 100               # the two scales every price and size of this market read under
    point_value_micro: int = 1_000_000
    short_allowed: bool = True

@dataclass(frozen=True, slots=True)
class LiquidityOrder:                        # one drained intent, carrying no identity at all (R114)
    side: str                                # "buy" | "sell"
    kind: str                                # "market" | "limit"
    size_milli: int                          # > 0; size * MILLI on a binary, size on a continuous instrument (R148, R173)
    limit_price_bp: int | None               # the resting price L, None for a market order
    resting_since_ms: int | None             # the bar the limit order was drained at, None otherwise

@dataclass(frozen=True, slots=True)
class Fill:
    price_bp: int                            # in the instrument's ticks (1..9_999 on a binary), inside the envelope below
    base_price_bp: int                       # the price before impact; == price_bp for a limit fill
    slippage_bp: int                         # >= 0; price_bp - base_price_bp on a buy, the reverse on a sell
    filled_milli: int                        # >= 0
    unfilled_milli: int                      # >= 0; filled_milli + unfilled_milli == order.size_milli
    unfilled_reason: str                     # "none"|"volume_cap"|"cash"|"zero_volume"|"no_cross"|"no_liquidity"
    price_source: str                        # "open"|"quote"|"limit"|"impact"|"mm"|"event" (event only from event_fill, 17.3)
    role: str                                # "taker" for a market order, "maker" for a resting limit fill
    fee_cents: int                           # >= 0, exactly rule 5 below (the per-kind fee_cents call, R173)

@dataclass(frozen=True, slots=True)
class ObservedFlow:                          # the one channel a model carries state through
    market_id: str; t_ms: int
    bought_milli: int; sold_milli: int; n_fills: int; last_fill_price_bp: int

class LiquidityModel(Protocol):
    model_id: str                            # one of LIQUIDITY_MODELS; the runner checks it against config
    params_hash: str                         # sha256(canonical_json(params)), "" when the model has none
    def quote_bar(self, market_view: LiquidityMarketView, bar: Bar,
                  orders: Sequence[LiquidityOrder], *, schedule: FeeSchedule,
                  now_ms: int,
                  bar_prev: Bar | None = None) -> tuple[Fill, ...]: ...   # one Fill per order, in the same positions
        # bar_prev (ruling R214, declared here and applied by E2 in the next lot): the instrument's previous
        # bar from the dataset, None only on its first bar, so the half-spread floor of 17.4 is a function
        # of the tape and not of the call sequence
    def on_bar_end(self, observed_flow: ObservedFlow) -> None: ...

def cap_milli(bar: Bar, *, config: RunConfig, source: str) -> int: ...
def allocate_cap(orders: Sequence[LiquidityOrder], *, cap_milli: int) -> tuple[int, ...]: ...
def envelope_bounds(bar: Bar, *, kind: str = "binary") -> tuple[int, int]: ...   # (low, high) after clamp_price (R173)
def clamp_price(x: int, *, view: LiquidityMarketView) -> int: ...     # clamp_price_bp on a binary, 1..PRICE_TICKS_MAX otherwise
def slippage_ticks(base: int, *, config: RunConfig, taken_pct: int, view: LiquidityMarketView) -> int: ...  # 8.6 step 4 (R173)
def finalise_fill(*, quoted_bp: int, base_bp: int, order: LiquidityOrder, bar: Bar, filled_milli: int,
                  unfilled_reason: str, price_source: str, schedule: FeeSchedule,
                  market_view: LiquidityMarketView | None = None) -> Fill: ...   # None reads as a binary view (R173)
def truncate_for_cash(fill: Fill, *, max_filled_milli: int, schedule: FeeSchedule,
                      market_view: LiquidityMarketView | None = None,
                      order: LiquidityOrder | None = None) -> Fill: ...   # the side and role of the re-established fee (R214)
def make_liquidity(config: RunConfig, *, params: Mapping[str, object] | None = None) -> LiquidityModel: ...
def event_fill(order: LiquidityOrder, *, price_ticks: int, schedule: FeeSchedule) -> Fill: ...   # 17.3, ruling R152
def half_spread_ticks(bar_prev: Bar, bar: Bar, *, schedule: FeeSchedule) -> int: ...             # 17.4, ruling R156;
                                                          # Bar is 7.2's one bar type, its _bp fields in ticks (R173)

ENVELOPE_BREACHES = ("quote_inside_spread", "outside_range", "over_cap", "order_dependent",
                     "not_deterministic", "negative_fill", "size_not_conserved", "bad_reason", "bad_fee")
def check_envelope(model: LiquidityModel, *, market_view: LiquidityMarketView, bar: Bar,
                   orders: Sequence[LiquidityOrder], config: RunConfig,
                   schedule: FeeSchedule) -> tuple[str, ...]: ...
```

**How it is called.** `quote_bar` is called **once per (market, bar)** in the execute phase, with every
order drained on that market at that bar in one sequence, built in the canonical order of section 3
(agents by `agent_id`, then submission order), each with `size_milli = size * MILLI` on a binary and
`size_milli = size` on a continuous instrument, whose sizes are already milli-units (rulings R148 and R173),
and with `now_ms = t_ms` of the **execution** bar and the market's resolved `FeeSchedule`. It returns one `Fill`
per order, in the same positions. The batch shape is not a convenience: under the decision latency rule
every one of those orders was queued a bar earlier and arrives at the same open, so a model that priced
them one at a time would be inventing an arrival sequence the tape never had, and rationing a scarce cap
fairly is impossible without seeing the whole batch (ruling R126). On a binary `Execution` takes
`filled = fill.filled_milli // MILLI` whole contracts and counts the remainder as unfilled: money is
integral, so a partial contract is not a fill; on a continuous instrument `filled = fill.filled_milli` and
nothing is truncated, because a milli-coin is a fill (rulings R148 and R173). `on_bar_end` is called once per (market, bar) after
`quote_bar` returns, in canonical market order, with the aggregate of what actually filled. Between those
calls a model may keep state; it may not read a clock, a `random.random` or a `uuid4` (preamble rule 4
applies to it as engine code), and it may not read the dataset.

**The envelope rule**, normative for every implementation, present and future:

1. **Never quote inside the observed spread when it is known.** With `low, high = envelope_bounds(bar)`,
   let `ask = min(max(bar.yes_ask_bp, low), high)` and `bid = min(max(bar.yes_bid_bp, low), high)` when
   the bar carries them. A **taker** buy quotes `price_bp >= ask`; a taker sell quotes `price_bp <= bid`; a
   resting limit fill is governed by 8.6's limit rule (`min(L, bar.open_bp)` for a buy, `max(L, bar.open_bp)`
   for a sell) and by rule 3, not by this rule, and `check_envelope` checks rule 1 on orders whose kind is
   `market` (ruling R214). The clamp comes
   first so that rules 1 and 3 cannot contradict each other (ruling R115). A bar with no quote is
   constrained by rule 3 and by the **half-spread floor** of section 17.4 (amendment C1b, ruling R156):
   with `hs = half_spread_ticks(previous bar, bar, schedule=schedule)`, a buy quotes `price_bp >=
   min(bar.open_bp + hs, high)` and a sell `price_bp <= max(bar.open_bp - hs, low)`, so that a tape
   without quotes still charges the spread its own ranges imply. On a binary schedule the floor is `0`
   and two identical flat bars estimate `0`, so 8.6 step 3's "else `bar.open_bp`" is unchanged on the
   demo pack.
2. **Never fill more than the tape allows.** Over one (market, bar), the sum of `filled_milli` across
   every agent and every order, market and limit alike, is at most
   `cap_milli(bar, config=config, source=source)`, which is
   `(bar.volume_milli * config.volume_cap_permille) // 1_000`. **The reconstructed exemption of ruling
   R41 is restated here and is part of the envelope**: a market with `source == "reconstructed"` carries
   no volume because its source has none (PRD 3.3), not because nothing traded, so rule 2 does not apply
   to it, `taken_pct = 0` and `slippage_bp = 0`. Inventing a volume the source never had would invent a
   cap and a slippage with it, and the demo pack, the only committed dataset, would fill nothing.
3. **Never fill outside the bar.** `bar.low_bp <= price_bp <= bar.high_bp`, and `price_bp` is a legal
   price under `clamp_price` (`1..9_999` through `clamp_price_bp` on a binary, `1..PRICE_TICKS_MAX` on a
   continuous instrument, ruling R173). A model may widen a spread; it may not print a price the tape
   never showed.
4. **Never let arrival order matter.** A model's price schedule for one (market, bar) is fixed by what it
   knew at that bar's open: the market view, the bar, its own state from earlier bars, and the batch it is
   handed as a set. It may not depend on the identity of the agent (it is not given one, ruling R114) nor
   on an order's position in the sequence. Operationally: **the multiset of returned `Fill`s is invariant
   under permutation of `orders`, and the fill returned for a given order does not depend on where in the
   sequence it sat.** Two orders that are equal field by field are the same order to the tape, so which of
   them takes an odd milli-contract is not a difference this rule can see. A shared cap consumed first
   come first served **fails** this rule, which is why `historical` rations pro rata (8.6 step 2, rulings
   R127 and R141): under arrival rationing, two buys of 80 and 40 against a cap of 100 fill 80 and 20 in
   one sequence and 60 and 40 in the other, and both the multiset and the aggregate notional move.
5. **Never invent a fee.** `fill.fee_cents == fees.fee_cents(schedule, size=fill.filled_milli // MILLI if
   market_view.kind == "binary" else fill.filled_milli, price_bp=fill.price_bp, role=fill.role,
   side=order.side, tick_size_micro=market_view.tick_size_micro,
   point_value_micro=market_view.point_value_micro)` exactly (ruling R173: on a binary the call is 8.8's to
   the letter, on a continuous instrument the size is the milli size and a `// MILLI` would turn a one
   milli-coin fill into a fee on nothing), with `fill.role == "taker"` when `order.kind` is
   `market` and `"maker"` for a resting `limit` fill; a fill truncated by `truncate_for_cash` takes the side and
   the role of its own order, which the function receives (ruling R214). The equality is stated over **the fill the journal
   writes**, not over an intermediate the journal never sees: `finalise_fill` establishes it and
   `truncate_for_cash` re-establishes it after 8.6 step 5 shrinks a fill against cash (ruling R130). Fees
   are venue data (section 8.8); an adversary that could discount them would be rewriting the venue rather
   than the spread.

**`check_envelope` is the function every implementation must pass.** It drives `model.quote_bar` over
`orders` (a sequence of `LiquidityOrder`, market and limit alike, so the limit path of 8.6 is inside the
check rather than outside it), twice in the given order and once per permutation of it, and
returns the tuple of `ENVELOPE_BREACHES` it observed, empty when the model is inside the envelope: rules
1, 3 and 5 per fill, rule 2 on the batch total, `order_dependent` when a permutation changes the multiset
of fills, `not_deterministic` when the same driving twice differs, `negative_fill` and
`size_not_conserved` on the arithmetic of `Fill`, `bad_reason` on a reason outside the enum or on
`"none"` with a non-zero `unfilled_milli`, `bad_fee` on rule 5 including a `role` that contradicts
`order.kind`. Each of the three implementations passes it as a hypothesis property test in its own test
file: E2 in `tests/test_execution.py`, R1c in `tests/test_liquidity.py`,
R4a in `tests/test_adversary_mm.py`. E2's test drives it on a binary view **and** on a continuous view
(`kind = "spot_crypto"`, `tick_size_micro = 10_000`, `point_value_micro = 1_000_000`, bars around
`6_341_257` ticks, milli sizes down to `1`), so a `clamp_price_bp`, a `// MILLI` or an absolute bp slippage
left on a continuous path fails as `outside_range` or `bad_fee` (ruling R173). Realism is a constraint, not a parameter, and this function is where
that sentence is executable.

**The three implementations.**

| `model_id` | Owner, file, wave | What it is | `price_source` it may emit |
|---|---|---|---|
| `historical` | **E2**, `engine/liquidity.py`, wave 2 | Section 8.6 steps 1 to 4: the bar's quote when it has one, else the bar's **open**, plus the volume cap and the linear slippage of `RunConfig`. `params_hash` is `""`: it has no parameter the config does not carry | `open`, `quote`, `limit` |
| `calibrated_impact` | **R1c**, `engine/liquidity.py` (E2's file, ruling R123), wave 7 | The impact coefficient of the market's liquidity decile, regressed from the tape by `pmx.data.impact` and stored in the dataset manifest's `impact` block; a fill beyond the cap pays that impact. Limit orders gain a queue position: a resting order fills only after the observed volume at or through its price exceeds a queue estimate. **Both the regression and the decile ranking are fit on the training fold only** (ruling R135) | `open`, `quote`, `limit`, `impact` |
| `adversarial_mm` | **R4a**, `adversary/mm.py`, wave 10 | Spreads, depth per price level and impact as functions of its genome, the market view, the current bar and its own `ObservedFlow` history, parametric first and learned later. Those four are its only inputs (ruling R134): the hive's reputations are per `(agent_id, category)` and are built from settled markets, so reading them would breach both R114 and section 7.9. The aggregate flow it already sees **is** the population's revealed behaviour, with no identity on it | `mm`, `limit` |

**The `RunConfig` field and its footprint** (ruling R112; `RunConfig` is section 8.1, D1's file, and gate
G2 applies the two lines):

```python
    liquidity: str = "historical"              # one of LIQUIDITY_MODELS
    liquidity_params_hash: str = ""            # sha256(canonical_json(params)) of the model, "" when none
```

- **Config**: both fields are in `to_dict()`, therefore in `config_hash`, therefore in the run id
  (section 2). Two runs that differ only in the liquidity they faced have different run ids, different
  directories and different journals, which is ruling R8's argument applied to the tape.
- **Manifest**: `runs/<run_id>/manifest.json` carries `config` verbatim (section 9.5), so it carries both
  names with no new top-level field. `data/datasets/<name>/manifest.json` carries the `impact` block that
  `calibrated_impact` reads (R1c, `dataset.v1.json`), so a run that used a calibrated model can be traced
  to the calibration that produced it. **That block is fit on the training fold and says so**
  (ruling R135): it carries `fit_fold: "train"`, `fit_t1_ms` (the last resolution the regression saw),
  `params_sha256`, `impact_bp_per_pct_by_decile` and `n_markets_fit`, and `liquidity_decile` ranks a market
  by its training-fold volume. Without the restriction a claim made on the sealed fold would be priced by
  coefficients regressed on the sealed fold, and its PnL half would be contaminated even though the agent
  never saw a forbidden field, exactly as `model_card.v1.json` pins `train.fold` to `"train"` and 8.1
  raises `LeakError` on a memory snapshot from a later run. `pmx claim` (section 12.8) refuses a
  `calibrated_impact` run whose `impact.fit_t1_ms` exceeds the claim's `t0_ms`, and R1c's "two builds give
  identical coefficients" test therefore pins a train-fold quantity.
- **Journal**: `run_started.config` carries both names, and that is the whole journal footprint of the
  choice. Per fill, `filled.price_source` says which path priced it (`open`, `quote`, `limit`, `impact`,
  `mm`), which is why R111 widens that enum. `vwap` is **not** in that list and is not a value a
  `LiquidityModel` may return (ruling R138): R113 abolished the vwap base and none of the three
  implementations may emit it; it survives in `journal.v2.json`'s enum only so that a journal written
  before the amendment still validates. `RunProjection` (section 12.11) exposes `liquidity` and
  `liquidity_params_hash`, rebuilt from `run_started.config` alone, so `pmx replay` still needs nothing
  but the journal and the leaderboard can show the historical and the adversarial column side by side.
- The runner raises `InvalidConfigError` when it is handed a model whose `model_id` or `params_hash`
  disagrees with the config. A journal may not claim a liquidity it did not run under.

### 16.2 The decision latency rule

**An action decided on bar `t` executes at the open of bar `t + interval_ms`.** There is no fill inside
the bar the agent has just observed. On a session calendar every `t + interval_ms` of this subsection reads
as **the instrument's next bar** and every `t - interval_ms` as its previous bar (section 17.2, ruling
R192): a decision on Friday's last bar fills at Monday's first bar and its `order_placed.decided_at_ms` is
Friday's bar. `DECISION_LATENCY_BARS = 1` is a constant of `pmx.types`, not a
`RunConfig` field (ruling R107): a run that could switch the latency off would be a run whose fills the
tape never had to honour, and every claim made under it would be worth less than the paper it is written
on.

**What it changes in the phase order of 8.2.** Not the order: `PHASE_ORDER` (section 9.1), the `phase`
constant of every event of 9.2 and what `verify_journal` compares against are all unchanged (ruling
R108). Two rows of the table change meaning:

- **`decide` (phase 3)** additionally hands every order-producing action to `Execution.place`, which
  **queues** it against `(agent_id, market_id, item_index, decided_at_ms = t)`. `place` emits no event,
  moves no cent and reserves nothing.
- **`execute` (phase 4)** drains the queue accepted at `t - interval_ms`, in `agent_id` order then
  submission order, and prices it against bar `t` through the run's `LiquidityModel`. Every execute-phase
  event of 9.2 comes from here, exactly as before, so section 8.9's accounting invariant and section
  9.3's one-event-per-money-movement rule are untouched. **The runner drives it over
  `Execution.pending_market_ids(t_ms=t)`, not over the bar slice** (ruling R131; the tuple also carries every
  instrument with a resting order of any agent, ruling R213): the queue's own market
  set is the only correct enumeration, because a market that closed or settled at `t - interval_ms` is in
  no tuple of E1's `BarSlice` at `t` and is still owed the rejection the table below promises. The runner
  resolves each `Market` from the dataset it was handed, and E5 asserts that every item `place` accepted
  produces exactly one execute-phase event.

`execute` stays **after** `observe`, which is less physical and is the only safe order: a fill at bar
`t`'s open lands in the agent's cash and in `avg_cost_bp`, so an observation built after it would carry
the price of a bar that has not completed, which is the leak section 5.4 exists to prevent. The agent
learns of its fill in the observation of `t + interval_ms`, by which time bar `t` is completed and its
open is public.

**What it changes in the tradable rule of 5.3 (ruling R9).** Nothing about where a fill may land: only a
bar entirely inside the trading window can fill, and no `filled` event exists at `bar_of(close_at_ms)` or
at `bar_of(resolved_at_ms)`. What is added is the predicate a decision is worth taking under:

```
actionable(m, t) = tradable(m, t + interval_ms)
```

A market's last actionable bar is therefore one bar before its last tradable bar. **The action decided on
the last tradable bar has nowhere to fill, and that is the rule**, not a defect to be patched: the agent
decided on information that ends at the last completed bar, and the tape it would have to trade against
is the bar that carries the close and the outcome.

**What it changes in the fill rules of 8.6.** Step 0 is now also the expiry of a deferred action: at the
execute phase of bar `t`, an item drained from the queue whose market fails `tradable(m, t)` is
`order_rejected(not_tradable)` and nothing else. Steps 1 to 4 move into `historical` (16.1) and step 3's
fallback base moves from `bar.vwap_bp` to `bar.open_bp` with `price_source = "open"`. The limit rule is
unchanged and already priced against `bar.open_bp`; `placed_at_ms`, and therefore `expires_at_ms`, is the
bar the order was drained at, so `ttl_bars` counts from the bar the order actually rests. Step 5, the
netting and the cash truncation, is unchanged and still `Execution`'s.

**What the journal records.**

| Case | What is written, and where |
|---|---|
| An action is decided | `action_received` at bar `t`, phase `decide`, with the intent in `intents` exactly as today. The queue itself is never journaled: it is state the journal can rebuild, and a queue event would be a projection of `action_received` (section 9.5 forbids widening the journal with derived numbers) |
| The action executes | `order_placed` at bar `t + interval_ms`, phase `execute`, carrying `decided_at_ms = t` (ruling R111), then `filled` and `fee_charged` as today. `decided_at_ms` is not decoration: `item_index` indexes the **previous** bar's `action_received`, and without it a rejection cannot be traced to the intent that caused it |
| The action expires | `order_rejected` at bar `t + interval_ms`, phase `execute`, `reason = "not_tradable"`, `decided_at_ms = t`, and no `order_placed`. This covers the market that closed, the market that settled, and the action decided on the last tradable bar. The settled market is in none of `BarSlice`'s four tuples at `t + interval_ms`, which is why the drain is driven by `pending_market_ids` (ruling R131) |
| The agent was ruined between deciding and executing | `order_rejected(reason="ruined", decided_at_ms=t)` at the execution bar. The ruin itself is `agent_ruined` at the close phase of bar `t`, as today |
| The action was decided on the run's last bar | Nothing beyond `action_received`. There is no execute phase after `t1_ms - interval_ms` to drain it, so it is dropped; E5's test states the rule as "no `order_placed` carries a `decided_at_ms` equal to its instrument's last actionable bar or later" (`t1_ms - interval_ms` on a `continuous` calendar, ruling R192) |

Two consequences are stated rather than defaulted away. `target` is the safe idiom under latency, because
it names an absolute position and a target repeated while a fill is in flight becomes a no-op once the
fill lands; a `limit` repeated on consecutive bars rests **twice**, and the scripted families of 10.5 are
written against that. And the observation at the execution bar still shows the pre-fill portfolio, which
is the price of keeping `execute` after `observe`.

### 16.3 `EventCluster` and `Constraint`

Computed at build time by `pmx.data.clusters` (R1b), sealed with the dataset, and **never a label to an
agent**. The schema is `src/pmx/schemas/cluster.v1.json`; the fixture is
`tests/fixtures/contract/clusters.sample.json`.

```python
# pmx.data.clusters (R1b)
@dataclass(frozen=True, slots=True)
class MatchReason:
    kind: str                # "wiki_subject"|"question_similarity"|"event_ticker"|"venue_duplicate"
                             # |"venue_complement"|"resolution_date"|"manual"
    asof: bool               # False for "resolution_date" and "manual", always (they are hindsight)
    detail: str              # the shared subject, the ticker, the ratio, the reviewer's sentence
    score_permille: int

@dataclass(frozen=True, slots=True)
class EventCluster:
    cluster_id: str          # "ec-" + sha256(canonical_json(sorted market_ids))[:16]
    market_ids: tuple[str, ...]          # >= 2, canonical market order (section 3)
    providers: tuple[str, ...]; currencies: tuple[str, ...]      # "usd" | "mana" (section 7.2)
    asof: bool               # every reason is as-of and the source is the matcher
    score_permille: int      # the MINIMUM over the reasons: the matcher is conservative by construction
    resolution_span_ms: int  # max(resolved_at_ms) - min(resolved_at_ms) over the members, and -1 when
                             # asof is True, because an as-of cluster never read a resolution date (R132)
    source: str              # "matcher" | "manual"
    reasons: tuple[MatchReason, ...]     # >= 1, sorted by (-score_permille, kind, detail)

@dataclass(frozen=True, slots=True)
class Constraint:
    constraint_id: str       # "cn-<kind>-" + sha256(canonical_json([kind, market_ids, direction]))[:12]
    kind: str                # "sum_to_one" | "implies" | "monotone_ladder" | "complement"
    market_ids: tuple[str, ...]          # ordered by the relation, see below
    direction: str           # "non_increasing" | "non_decreasing" for a ladder, else "none"
    cluster_id: str | None   # when not None, every id of market_ids is a member of that cluster (R143)
    asof: bool; score_permille: int
    source: str              # "event_ticker" | "venue_duplicate" | "venue_complement" | "manual"
    reasons: tuple[MatchReason, ...]

def constraint_residual_ppm(kind: str, prices_ppm: Sequence[int], *, direction: str = "none") -> int: ...
```

**A constraint that names a cluster lives inside it** (ruling R143): when `cluster_id` is not `None`,
every id of the constraint's `market_ids` is in that cluster's `market_ids`, and a matcher that finds a
relation reaching outside the cluster **extends the cluster** rather than filing the constraint against a
partial one. Without the invariant R2b and R2c would disagree about which markets a `divergence` or a
`logic` event may cite, and 16.4's `opportunity_id`, which hashes `cluster_id` and `constraint_id`
together, would name a pair that does not exist. The check is across records, so
`tests/test_contract_schemas.py` asserts it on the fixture rather than the schema.

`market_ids` is ordered by the relation's own semantics, because the residual is not symmetric:
`(antecedent, consequent)` for `implies`, ascending threshold or ascending date for `monotone_ladder`,
canonical market order for `sum_to_one` and `complement`. `constraint_residual_ppm` is the one
implementation of the four residuals and both R1b and R2c call it: `sum(p) - PPM_ONE` for `sum_to_one`,
`p[0] - p[1]` clipped below at zero for `implies` (A implies B, so `p(A) <= p(B)`), the largest violating
step along the tuple for `monotone_ladder`, `p[0] + p[1] - PPM_ONE` for `complement`. A residual is zero
when the relation holds, signed when it does not, and it is computed over prices only.

**On disk, inside the dataset and inside its hash** (ruling R117):

```
data/datasets/<name>/clusters/clusters.json     canonical_json + "\n", cluster.v1.json
data/datasets/<name>/clusters/overrides.json    the hand-written review, cluster.v1.json#/$defs/override_file
```

**Neither file carries a `dataset_hash`** (ruling R128). Both are inside the walk of 4.3, so their bytes
are an input to `dataset_hash`, and a file that also held that hash would be an unsatisfiable fixed point:
`pmx data seal` could never fill it and `pmx data verify` could never check it. What ties a cluster
document to its dataset is where it sits and what the manifest says: `clusters.json` carries
`dataset_name` and `overrides_sha256`, the manifest's `clusters` block repeats the matcher's parameters,
and `dataset_hash` covers the bytes of both files. This is the same argument that excludes `manifest.json`
itself from the walk.

`overrides.json` is written by a human after reviewing the UI (PRD v3 3.2 and the risk table), holds
`force` and `forbid` entries, and is hashed into `clusters.json.overrides_sha256`. Both files join
`markets/`, `news/` and `wiki_asof/` in the walk of section 4.3, so `pmx data seal` and `pmx data verify`
cover them and a dataset cannot be reviewed after it is sealed. A dataset with no `clusters/` directory
hashes exactly as it does today.

**Manifest block** (`dataset.v1.json`, applied by gate G7):

```
clusters {matcher_version, min_score_permille, resolution_tolerance_ms, overrides_sha256,
          n_clusters, n_clusters_asof, n_cross_venue, n_constraints, per_kind {sum_to_one, implies,
          monotone_ladder, complement}, n_markets_clustered}
```

**The visibility rule.** Cluster membership is partly a function of `resolved_at_ms` (dates within a
tolerance) and of a human who could see the whole window, and both are forbidden by section 7.9. So:

- No `cluster_id`, no `constraint_id`, no `MatchReason`, no `score_permille`, no override and no
  detector output ever appears in an `Observation`, a prompt, a research result or a hive entry. Section
  7.9's list is extended by exactly those names and E1's poisoned-future test injects one of each.
- A cluster whose formation **consulted `resolved_at_ms` in any way** carries `asof: false` and is
  **analysis only**: its arithmetic may not reach a feature vector either (section 16.5, ruling R116).
  "In any way" is the whole rule (ruling R132): a stored `resolution_date` reason and a `manual` reason
  are the obvious cases, and so is the `resolution_tolerance_ms` filter, because a pair kept or dropped by
  a tolerance on resolution dates is a pair **selected with hindsight** whether or not a reason recorded
  it. The matcher therefore stores a `resolution_date` reason whenever the tolerance decided anything
  about a grouping, and an `asof: true` cluster is matched by content only: `wiki_subject`,
  `question_similarity`, `event_ticker`, `venue_duplicate` and `venue_complement`. `resolution_span_ms` is
  `-1` on an as-of cluster and `cluster.v1.json` enforces it, so the record itself shows that no
  resolution date was read; analysis recomputes the span from the dataset when it wants it, where
  hindsight is allowed.
- The other half of the rule is equally normative: **the cluster's other markets' prices are visible
  exactly as any market's prices are**, because a human trader would see them. An agent reaches a peer
  through the ordinary `MarketView` of that market when the run carries it, and **the engine never adds a
  market to an observation because it is a cluster peer**, which would leak the grouping through the
  market set.
- `block_key` (section 12.4) gains a keyword-only `cluster_id` (ruling R118): two venues' markets on one
  event are one block, not two independent draws. This is the engine's own use of the grouping, in the
  statistics, where hindsight is allowed and the agent is not looking.

### 16.4 `OpportunityEvent` and the analysis outputs

A detector is a deterministic projection of the dataset. It is not an agent, it never writes a journal
and it never reads the sealed fold (architecture rule 8). Its job is to say which inefficiencies exist
and how big they were, so that agents are built against measured edges. The schema is
`src/pmx/schemas/opportunity.v1.json`; the fixture is
`tests/fixtures/contract/opportunity.divergence.json`.

```python
# pmx.analysis.report (R2e) declares these; each detector emits them
DETECTORS = ("news_lead", "divergence", "logic", "comparative")

@dataclass(frozen=True, slots=True)
class Evidence:
    kind: str                # "price" | "news" | "constraint" | "cluster" | "stat"
    ref: str                 # a market id, a news id, a constraint id, a cluster id, or a metric name
    t_ms: int; value: int
    unit: str                # "ppm"|"bp"|"cents"|"ms"|"milli"|"count"|"micro"|"permille"

@dataclass(frozen=True, slots=True)
class OpportunityEvent:
    opportunity_id: str      # "op-<detector_id>-" + sha256(canonical_json(
                             #   [detector_id, sorted(market_ids), window[0], window[1],
                             #    cluster_id, constraint_id]))[:16]
    detector_id: str         # one of DETECTORS
    market_ids: tuple[str, ...]
    cluster_id: str | None; constraint_id: str | None
    window: tuple[int, int]  # (start_ms, end_ms): first and last bar open it was observed at, inclusive
    duration_bars: int
    size_ppm: int            # the size of the inefficiency in probability units
    size_net_bp: int         # net of both venues' fees and of the spread envelope; negative when it does not pay
    payoff_cents: int        # the ex-post payoff of the paper combination UNDER THE LATENCY RULE of 16.2
    currency: str            # "usd" | "mana" | "mixed"
    tradable_for_money: bool # False as soon as one leg is play money, whatever the size
    evidence: tuple[Evidence, ...]
```

`payoff_cents` is measured the way the engine would have traded it: entered at the open of the bar after
the one the signal was visible on, priced inside the envelope of 16.1, charged the fee schedule of 8.8. A
detector that scored itself at the price it saw would be measuring a fill nobody could have had.

**The currency label is structural, not a caveat in prose** (PRD v3 4.2). Kalshi is `usd`, Manifold is
`mana`, a pair of the two is `mixed`, and `mixed` or `mana` forces `tradable_for_money = false`: a gap
between a real-money and a play-money venue is informative about the play-money side's pricing and is not
an edge anyone can bank. Every claim, card and leaderboard row stays per provider (section 12.6 pools
nothing across providers), and the schema refuses an event that labels itself otherwise.

**Output layout** (generated, git-ignored, ruling R125):

```
analysis/<dataset_name>/<detector_id>.json   opportunity.v1.json: params, params_sha256, the block-bootstrap
                                             summary with its permutation null, and the events
analysis/<dataset_name>/opportunity_map.json one row per detector: lower bound, interval, null,
                                             n_detectors_run, currency, params_sha256
                                             (mapped fields: payoff_lb_micro and null_lb_micro beside
                                             their bounds, never an embedded Interval.to_dict(), R219)
analysis/<dataset_name>/manifest.json        dataset_name, dataset_hash, detectors run, pmx_version,
                                             contract_version, features_hash when a detector used features
```

Every headline number is a **lower bound** from the block bootstrap of 12.4 with the permutation null
beside it, and `n_detectors_run` is on every file so a reader can deflate for the number of detectors
that were tried (PRD v3 section 11). The UI reads these files through `api/routes_analysis.py` (R2e); the
Opportunities tab shows one card per detector with its bound, its interval and its null.

### 16.5 `features.v1`, the `torch_policy` genome and the quantisation rule

**The layout.** `pmx.features.spec` (R3a) declares `FEATURES: tuple[FeatureSpec, ...]` in vector order.
Each entry carries `index`, `name`, `unit`, `lo`, `hi` (inclusive clamp bounds, a value outside is
clamped and never dropped), `scale` (the divisor of the float view), `source` and `asof_only`.
`FEATURES_VERSION = "features.v1"` and `features_hash = sha256(canonical_json([spec.to_dict() for spec in
FEATURES]))`. The hash enters the run manifest, every `ModelCard` and every analysis manifest that used a
feature, so a policy trained on one layout cannot be scored against another. The declaration document is
`features.v1.json` and the normative layout is the fixture
`tests/fixtures/contract/features.spec.json`: thirty-seven integer fields in seven blocks (market view,
bars, calendar, category, news, cluster and constraint, portfolio), which R3a implements exactly, in that
order, with those names, units, bounds and scales.

**Only as-of data enters a feature.** The ban list is section 7.9's, in full: no `resolution`, no
`resolved_at_ms`, no `final_price_bp`, no `hardness_tags`, no `quality`, no `n_bars`, no `fold`, no bar
that has not completed at `now_ms`. Two additions belong to this amendment: no field of an
`OpportunityEvent`, ever (a detector's verdict is hindsight with a lower bound attached), and no cluster
or constraint arithmetic unless the cluster carries `asof: true` (ruling R116), which is why every
feature whose `source` is `cluster` or `constraint` declares `asof_only: true` and the schema refuses it
otherwise. A third addition closes the membership half of the same hole (ruling R133): **a cluster or
constraint feature at `now_ms` is computed over the members satisfying `listed(peer, now_ms)` and over no
others**, each from its own last completed bar. `cluster_peer_count` (index 28) counts those members only,
and `cluster_gap_bp` (index 27) is undefined and clamped to its `lo` when fewer than two qualify. A static
whole-window membership would otherwise put "a second venue will list this event" into a feature vector,
which is future information and correlates with exactly the events that turn out to matter; the engine
half of the rule was written carefully in 16.3 and the feature half was not. E1's poisoned-future test is
extended to the feature builder: the same injected strings, the same assertion by content match, plus a
fixture where a peer is created after `now_ms` and an assertion that `cluster_peer_count` does not move.

**The float view is one way.** `pmx.features.view.float_view(values) -> list[float]` clamps to
`[lo, hi]` and divides by `scale`, in `float32`. It may be called from `learn/`, from `adversary/train/`
and from the inference boundary of `pmx.agents.families.torch_policy`, and from nowhere else (ruling
R140): a card whose `inference_kind` is `cpu_float32` has to turn an integer feature vector into floats
somewhere, and that somewhere is the boundary this subsection already names, not a directory a backtest
never loads. The confinement was never about the directory, it was about what comes back: no float returns
through it, there is no inverse, nothing built from it is journaled, hashed or compared, and a feature
vector on disk is integers (`features.v1.json#/$defs/feature_vector`).

**The `torch_policy` genome.** `Genome` gains a fifth component beside `prompt` (ruling R119):

```python
    card: "ModelCard | None"      # torch_policy only; null for every other family, always in to_dict()
```

The card is `model_card.v1.json`: `model_id` (`"mc-" + weights_sha256[:16]`), `weights_sha256`,
`weights_bytes`, `architecture`, `n_parameters`, `inference_kind`, `features_version`, `features_hash`,
the `train` block (dataset, fold, window, algorithm, steps, seeds, framework, device) and the
`validation` block (the walk-forward numbers with their bootstrap, as **mapped** fields (`skill_lb_micro`,
`null_lb_micro` and the bound's parts) and never an embedded `Interval.to_dict()`, ruling R219). Because the card is inside the
genome, `genome_hash` covers the weights hash, and a claim names the exact model it was made with. The
weights file itself lives in `models/<weights_sha256>.pt`, is git-ignored, and is never inside a hash
other than its own digest. `train.fold` is `"train"`: a card trained on anything else is a contaminated
card, and the sealed fold is unreachable outside `pmx.optimizer.claims` (section 12.7).

**The quantisation rule.** A policy's outputs become integers **before** anything is journaled:
`pmx.features.quantise.ppm_from_unit(x) -> int` (round half up, clamped to `[0, PPM_ONE]`) for a
probability and `position_from_unit(x, *, max_position) -> int` for a position in whole contracts. This
is the fifth legal float site of preamble rule 3 (ruling R120), it lives at the inference boundary in
`pmx.agents.families.torch_policy`, and the float dies there: it is never journaled, never hashed and
never compared. Section 6.4 gains the matching honesty: a `torch_policy` run **replays** byte-identically
from its journal on any machine, which is what AC-16 asks and what the journal guarantees; it **reruns**
byte-identically only when its card declares `inference_kind == "integer_table"`.

**The torch rule.** Nothing outside `src/pmx/learn/` and `src/pmx/adversary/train/` imports `torch`,
`sklearn` or `sentence_transformers` (nor `transformers` or `peft`, the QLoRA path of R5c, which live in
`learn/` anyway). The engine, the agents, the scoring, the metrics and the analysis packages import none
of them; `torch_policy` runs an inference path that does not need them, which is what "replays without a
GPU" means. Architecture rule 7 enforces it. Those libraries are a `learn` extra in `pyproject.toml`
(U4's file, a contract issue for gate G9), never a core dependency.

### 16.6 The v3 module map and the three new architecture rules

Section 13 now carries a row for every file of PRD v3 section 10, each with exactly one owner taken from
`docs/PLAN_V3_WAVES.md`: `data/universe.py` (R1a), `data/clusters.py` (R1b), `data/impact.py` (R1c),
`data/embeddings.py` (R3b), `engine/liquidity.py` (E2, with R1c adding `calibrated_impact` by the
agreement of ruling R123), `analysis/*` (R2a to R2e), `features/*` (R3a), `learn/*` (R3c, R3d, R5c),
`agents/families/torch_policy.py` (R3e), `adversary/*` (R4a to R4d), `portfolio/*` (R5a, R5b),
`live/opportunities.py` (R6a), `cli_analyze.py` (R2e), `cli_learn.py` (R3d), `cli_adversary.py` (R4b),
`cli_portfolio.py` (R5a), and `tests/e2e/` (the gate of each rung, G7 to G11, so no package writes an
end-to-end test another package's gate must run). **Rung 0's own test has an owner too**:
`tests/e2e/test_e2e_0_base.py` belongs to **gate G6** (ruling R137), the last gate of part 1 and the first
point at which build, run, replay and claim all exist. PRD v3 section 9 makes the e2e suite cumulative,
and a rung's gate runs `tests/e2e/` in full and **fails when a delivered rung's file is absent**, so a
missing test cannot pass as an empty directory. Each new package's `__init__.py` belongs to the
amendment that opens its wave (ruling R122). `analysis/` and `models/` are generated and git-ignored.

Three rules join the six of `tests/test_architecture.py`, all three green on the tree of 2026-09-08:

7. **No torch, sklearn or sentence_transformers outside `learn/` and `adversary/train/`.** A module that
   imports a training library is a module a backtest cannot replay without one. `float_view` is not a
   training library and is not covered by this rule: it may also be called at the inference boundary of
   `agents/families/torch_policy.py` (ruling R140), which imports no such library.
8. **Nothing in `analysis/` writes a journal or reads the sealed fold.** A detector is a projection: it
   imports no `pmx.journal`, names no `Journal`, `read_journal` or `write_journal`, and neither names
   `open_sealed_test` nor carries the string `"sealed"` in code. Rule 3 already guards the one sealed
   accessor; this rule keeps a whole package on the analysis side of the line. It binds `analysis/` and
   **not** `pmx.rules` (ruling R294): the rule tester is the one emitter of four journal events (9.3), so
   it imports `pmx.journal` by design; what binds it is rule 3, the sealed fold, and the test scans
   `analysis/` alone for exactly that reason.
9. **`engine/liquidity.py` is the only place a fill price is computed.** `fill_price_bp` is assigned
   nowhere else in `src/pmx`; every implementation, wherever it lives, returns its quote through
   `finalise_fill`, which is where the envelope is applied and where that name is bound.

### 16.7 v3 identifier formats

The continuation of section 2's table. Every regex is a constant, and each lives beside its owning module
rather than in `pmx.types`, which shipped in wave 1 (ruling R121).

| Entity | Format | Regex | Assigned by |
|---|---|---|---|
| Event cluster | `ec-<sha256(canonical_json(sorted market_ids))[:16]>` | `^ec-[0-9a-f]{16}$` | `pmx.data.clusters` (R1b) |
| Constraint | `cn-<kind>-<sha256(canonical_json([kind, market_ids, direction]))[:12]>` | `^cn-(sum_to_one\|implies\|monotone_ladder\|complement)-[0-9a-f]{12}$` | `pmx.data.clusters` (R1b) |
| Opportunity | `op-<detector_id>-<sha256(canonical_json([detector_id, sorted market_ids, window start, window end, cluster_id, constraint_id]))[:16]>` | `^op-(news_lead\|divergence\|logic\|comparative)-[0-9a-f]{16}$` | `pmx.analysis.report` (R2e) |
| Model card | `mc-<weights_sha256[:16]>` | `^mc-[0-9a-f]{16}$` | `pmx.learn.cards` (R3d) |
| Detector | lowercase name | `^(news_lead\|divergence\|logic\|comparative)$` | this contract |
| Liquidity model | lowercase name | `^(historical\|calibrated_impact\|adversarial_mm)$` | this contract |

Every one of them is derived from content, never from a clock, a counter across runs or a UUID, so two
builds of the same raw data produce the same ids and a diff of two dataset directories is readable.

### 16.8 What amendment C1 does not own

C1 owns `docs/CONTRACTS_V2.md`, the nine schemas under `src/pmx/schemas/`,
`tests/test_contract_schemas.py`, `tests/test_architecture.py`, the fixtures under
`tests/fixtures/contract/` and the notes it added to `docs/PLAN_V2_WAVES.md`; section 13 now says exactly
that, where it used to name C0 alone (ruling R142).

**A section of this document is never a contract issue** (ruling R136). Every normative passage section 16
changes lives in a file C1 owns, so every one of them is amended **in place, in this pass**: the
preamble's float rule, 4.3's walk, 6.4's determinism table, 7.9's leak list, 8.1's `RunConfig`, 8.6's
steps and `Execution` surface, 9.2's three execute-phase rows, 12.4's `block_key`, 12.11's `run_backtest`,
and section 13's ownership rows. The same is true of the schemas: `journal.v2.json`, `dataset.v1.json` and
`cluster.v1.json` are C1's files under `src/pmx/schemas/`, so R111's enum widenings, R117's manifest block
and R128's removal are applied here rather than deferred. What is left below is code in another package's
file, listed with the gate that applies it, so that no package edits a file it does not own and no
requirement is lost:

| Issue | File and owner | Applied by |
|---|---|---|
| R129: the event dataclasses gain `decided_at_ms` on `OrderPlaced` and `OrderRejected`, and `journal.v2.json` promotes it from declared to `required` in the same commit. The schema half is already widened (both enums, `no_liquidity`, the property itself); what is deferred is only the `required` list, because `pmx.journal` cannot yet carry the field and `tests/fixtures/contract/journal.backtest.jsonl` is a pre-latency journal that has to be rebuilt with it | `pmx.journal` event dataclasses (D7); the `required` list of `src/pmx/schemas/journal.v2.json` and the backtest fixture (C1) in the same commit | gate G2, in the commit that lands E2 and E5 |
| R112: `RunConfig.liquidity` and `RunConfig.liquidity_params_hash` (section 8.1 already declares them) | `src/pmx/types.py` (D1) | gate G2 |
| R116: E1's poisoned-future test gains one of each cluster-derived name (section 7.9 already lists them) | `tests/test_observation.py` (E1) | gate G2 |
| R117 and R128: the walk gains `clusters/`, the manifest gains the `clusters` block, and neither cluster file carries a `dataset_hash` (sections 4.3, 7.1, 7.8 and `dataset.v1.json` already say so) | `pmx.data.loader.seal_dataset` and `verify_dataset` (D1) | gate G7 |
| R118: `block_key` gains a keyword-only `cluster_id` (section 12.4 already declares it) | `pmx.metrics.stats` (E4) | gate G2 (the argument), R1b (the value) |
| R119: `Genome.card`, and the run manifest's `features_version`, `features_hash` and `model_cards` | `pmx.agents.protocol` (A1), `pmx.engine.runner` (E5) | gate G3 (the field), gate G9 (the manifest) |
| R135: `pmx claim` refuses a `calibrated_impact` run whose `impact.fit_t1_ms` exceeds the claim's `t0_ms` | `pmx.optimizer.claims` (O4) | gate G7 |
| R125: `analysis/` and `models/` are git-ignored; the `learn` extra of `pyproject.toml` | `.gitignore` (C0), `pyproject.toml` (U4) | gate G8, gate G9 |

---

## 17. Instruments across kinds (amendment C1b)

`docs/PRD_V4_MULTI_ASSET.md` widens the arena from binary contracts to every traded market: crypto spot
and perpetuals, foreign exchange, equities and ETFs, futures. This section is the amendment the engine
wave (E1..E5) and the finance data wave (F1..F4, `docs/PLAN_V3_WAVES.md` wave 3b) are built against, and
it lands **before** the engine wave for the same reason section 16 did: execution, scoring and the runner
are written once, against sections 16 and 17 together, rather than rewritten when the first non-binary
instrument arrives. Everything below binds exactly as sections 1 to 16 do. Where it generalises earlier
text, the earlier text has already been amended in place and the change is a ruling in 15.9; no
binary-only sentence is left standing as if it were the whole rule.

Three sentences carry the whole design. **A binary contract is one instrument kind among six, and
nothing already written for it changes value**: `Market` keeps every v2 field, its prices in bp are its
prices in ticks, and every formula of sections 1, 8 and 12 is the `binary` row of the tables below. **A
continuous instrument has no resolution**: it is judged by its realised price path, a forecast made at
`t` for horizon `h` is scored against the price `h` bars later, a position is scored by the money it made
after every cost, and a position still open when the window ends is closed by the engine at the last
price, which is recorded as a fill and never as a mark. **Every cash flow that is not a fill is a dated
`CashEvent`** applied by execution in the settle phase and journaled once, so the accounting invariant
of 8.9 stays an identity over the journal alone for every kind.

### 17.1 The six kinds, the `Instrument` base and the integer price model

**The kinds are a closed enumeration** (`pmx.types.INSTRUMENT_KINDS`, ruling R144):

```python
INSTRUMENT_KINDS = ("binary", "spot_crypto", "perp", "fx", "equity", "future")
CONTINUOUS_KINDS = INSTRUMENT_KINDS[1:]
```

| Kind | Examples | Terminal settlement | Short side | Carry and corporate events | Stored as |
|---|---|---|---|---|---|
| `binary` | Kalshi, Manifold, Polymarket contracts | yes, at `resolved_at_ms`, to `SETTLE_YES_BP` or `SETTLE_NO_BP` | buy NO at `10_000 - price` (section 8.5, unchanged) | none | `market.v2.json`, `markets/<id>.json` |
| `spot_crypto` | BTCUSDT on Binance, XBTUSD on Kraken, BTC-USD on Coinbase | none; marked; forced flat at the window end | none (`short_allowed = false`): the short is the `perp` twin | none | `instrument.v1.json`, `instruments/<id>.json` |
| `perp` | BTCUSDT linear perpetual on Binance or Bybit | none; forced flat at the window end | native | `funding` every funding time, signed, from the venue's published history | `instrument.v1.json` |
| `fx` | EURUSD, USDJPY | none; forced flat at the window end | native (selling the base) | `carry` from a carry schedule when the run carries one; **off by default** (no schedule, no event) | `instrument.v1.json` |
| `equity` | AAPL, SPY | none; forced flat at the window end | allowed iff the instrument names a `borrow_schedule_id` | `dividend` on the ex-date, `split` on the effective date, `borrow_fee` per session day of a short | `instrument.v1.json` |
| `future` | ES, NQ, CL, GC, ZN, 6E continuous series | per contract, expressed as a `roll`; forced flat at the window end | native | `roll`: two fills at the two contracts' prices, the gap recorded and never traded through | `instrument.v1.json` |

**The `Instrument` base and where the fields live.** `Instrument` (`pmx.types`, D1's file, applied by
gate G2) is the common base every kind satisfies; `Market` **is** the binary instrument, keeps the name
and every field of section 7.2 in code, in the schema and on disk, and satisfies the base through the
mapping below. A continuous instrument is `pmx.types.ContinuousInstrument`, serialised by
`src/pmx/schemas/instrument.v1.json` (the schema refuses `kind == "binary"`, because a binary record is
`market.v2.json` and there is exactly one file shape per record). Nothing moves out of `Market`: the base
is a **view** of it, `Market.instrument` (a property D1 adds, ruling R144), and no code path reads
`tick_size_micro` off a `Market` field that does not exist. A record's own `kind` is the authority and the
view restates it: a reader takes `kind` off the record and the scale fields off the view (ruling R206).

| Base field | Type | Rule | On a `Market` (binary) |
|---|---|---|---|
| `id` | instrument id, section 17.8 | `<provider>-<slug>`; the field is still called `market_id` in every event, view and signature, for every kind (ruling R144: the name is the id namespace, not a claim about the kind) | `market.id` |
| `provider` | provider | the venue whose fee schedule applies, section 17.8 | `market.provider` |
| `vendor` | vendor | the data source the tape was read from, section 17.8; `yahoo` is unofficial and every claim on a `yahoo` tape carries the vendor caveat of PRD v4 section 8 | `== provider` |
| `symbol` | `str`, 1..64 | the venue's own symbol, verbatim | `market.provider_id` |
| `kind` | one of `INSTRUMENT_KINDS` | | `"binary"` |
| `currency` | `^[a-z]{3,5}$` | the quote currency, whose minor unit is the cash unit (`usd`, `usdt`, `eur`, `jpy`, `mana`) | `market.currency` |
| `tick_size_micro` | `int`, `1..TICK_SIZE_MICRO_MAX` | the smallest price increment in millionths of one quote unit | `BINARY_TICK_SIZE_MICRO = 100` |
| `point_value_micro` | `int`, `1..POINT_VALUE_MICRO_MAX` | the cash value, in millionths of the quote currency, of a one-point (one quote unit) move of one unit of position | `BINARY_POINT_VALUE_MICRO = 1_000_000` |
| `session_calendar_id` | calendar id, section 17.8 | section 17.2; `continuous` for crypto and for every binary | `"continuous"` |
| `fee_schedule_id` | fee schedule id | section 8.8 as generalised by 17.4 | `market.fee_schedule_id` |
| `borrow_schedule_id` | fee schedule id or `null` | 17.4; non-null only on an `equity` whose short side is allowed | `null` |
| `carry_schedule_id` | fee schedule id or `null` | 17.4; `perp` funding is **not** a carry schedule (it is data, per event); non-null only on an `fx` instrument in a run that models the swap | `null` |
| `listed_at_ms` | int | the first instant the instrument can carry a bar | `market.created_at_ms` |
| `delisted_at_ms` | int or `null` | the instant after which no bar exists; `null` for an instrument still listed at the freeze | `market.resolved_at_ms` |
| `short_allowed` | bool | from the kind table above; the importer sets it and the loader refuses a value the table forbids | `true` (the NO leg) |
| `interval_min` | `60` or `1440` | the grid of `bars`, one per dataset (section 5.3) | `market.interval_min` |

The remaining fields of `instrument.v1.json` are the continuous instrument's own: `url`, `description`
(0..4000), `category` (`crypto`, `finance`, `economics` or `other` from the importer's table),
`tags`, `twins` (instrument ids of the same underlying on other venues, declared by symbol mapping and
sorted; the cross-venue cluster hint of F1), `underlying_id` (a `perp` names its spot twin, a `future`
names nothing), `roll_source` (`"venue"` or `"vendor"`, `future` only, PRD v4 1.4), `first_price_ticks`,
`bars` (the `_ticks` bar record below), `trades` (the trade record below), `quality` (`n_trades`, `life_days`,
`volume_milli_total`, `traded_bars`, `tape_kind`, ruling R167), `cash_events` (the dated records of 17.3
that come from data), `source: "imported"` and `notes`.

The **file** shape of a bar (`instrument.v1.json#/$defs/bar`) is `Bar` with `_ticks` in place of `_bp` and
no payout bound: `t_ms, open_ticks, high_ticks, low_ticks, close_ticks, vwap_ticks` (all
`1..PRICE_TICKS_MAX`, `low <= open, close, vwap <= high`), `volume_milli >= 0`, `n_trades >= 0`,
`bid_ticks: int|null`, `ask_ticks: int|null` (`bid <= ask` when both present), `open_interest_milli:
int|null`; the file shape of a trade is `t_ms, price_ticks, size_milli >= 1, side in {"buy", "sell",
"unknown"}` (the taker's side). **In memory there is one bar type and one trade type for every kind**
(ruling R173): the loader maps the file's `_ticks` fields onto `pmx.types.Bar` and `pmx.types.Trade` field
by field (`open_bp <- open_ticks`, `high_bp <- high_ticks`, `low_bp <- low_ticks`, `close_bp <-
close_ticks`, `vwap_bp <- vwap_ticks`, `yes_bid_bp <- bid_ticks`, `yes_ask_bp <- ask_ticks`, `open_interest
<- open_interest_milli`, `price_bp <- price_ticks`, `side` kept), exactly as R148 keeps one event shape per
name, so `ContinuousInstrument.bars` is `tuple[Bar, ...]`, `ContinuousInstrument.trades` is
`tuple[Trade, ...]`, and `MarketView.bars`, `quote_bar`, `envelope_bounds`, `half_spread_ticks`, `bar_at`
and `bars_before` take a `Bar` whose `_bp` fields carry ticks; `bar_at` and `bars_before` are declared on
the `Instrument` base. There is no `InstrumentBar` and no `InstrumentTrade` Python type: the schema's `bar`
and `trade` definitions are the only place the `_ticks` spelling exists, and E1, E2 and E5 have one code
path per bar read. Bars are dense **on the instrument's session calendar** (17.2); a binary keeps 7.2's
dense grid verbatim (ruling R185).

**Prices, sizes and cash are three integers and one exact product.** For every kind:

```python
# pmx.types (D1, gate G2). CENTS_PER_UNIT, BP_ONE and PPM_ONE are section 1.2's.
MICRO = 1_000_000
MILLI = 1_000                                      # declared here, re-exported by pmx.engine.liquidity (R86)
NOTIONAL_DENOMINATOR = MILLI * MICRO * MICRO // CENTS_PER_UNIT      # 10**13, exactly
BINARY_TICK_SIZE_MICRO = 100                       # one basis point of a one-unit payout
BINARY_POINT_VALUE_MICRO = 1_000_000               # one unit of position pays one currency unit at 1.0
PRICE_TICKS_MAX = 10**12
SIZE_MILLI_MAX = 10**12
TICK_SIZE_MICRO_MAX = 10**9
POINT_VALUE_MICRO_MAX = 10**12
NOTIONAL_CENTS_MAX = 10**15                        # one fill or one cash event; bad_size beyond it
INT63_MAX = 2**63 - 1                              # every STORED integer fits; products need not

def notional_micro(size_milli: int, price_ticks: int, tick_size_micro: int, point_value_micro: int) -> int:
    return size_milli * price_ticks * tick_size_micro * point_value_micro     # exact, never stored

def cash_out_cents(size_milli, price_ticks, tick_size_micro, point_value_micro) -> int:   # what the agent pays
    return -((-notional_micro(size_milli, price_ticks, tick_size_micro, point_value_micro)) // NOTIONAL_DENOMINATOR)
def cash_in_cents(size_milli, price_ticks, tick_size_micro, point_value_micro) -> int:    # what the agent receives
    return notional_micro(size_milli, price_ticks, tick_size_micro, point_value_micro) // NOTIONAL_DENOMINATOR
def mark_value_cents(position_milli, mark_ticks, tick_size_micro, point_value_micro) -> int:  # signed
    n = notional_micro(abs(position_milli), mark_ticks, tick_size_micro, point_value_micro)
    return n // NOTIONAL_DENOMINATOR if position_milli >= 0 else -(-((-n) // NOTIONAL_DENOMINATOR))
def price_micro(price_ticks: int, tick_size_micro: int) -> int:                            # the price in micro quote units
    return price_ticks * tick_size_micro
```

- **One rounding, at the end, against the agent** (ruling R146). `cash_out_cents` rounds up,
  `cash_in_cents` rounds down, exactly as `cost_cents` and `proceeds_cents` do in section 1.2, and for the
  same reason: the engine never creates a cent by rounding and 8.9 is exact because the journaled delta is
  the integer the engine applied. A mark is `floor` for a long and `-ceil` of the liability for a short
  (the conservative side, as 8.7 already marks). PRD v4 1.2's "round half up, once, at the end" is read as
  "once, at the end": `round_half_up` is for a score and for a quantile, never for a cash movement, which
  would otherwise round for the agent half of the time and break the identity `proceeds <= cost` that the
  worked examples pin. No intermediate is rounded: the four-factor product is computed exactly in Python
  integers and divided once.
- **The binary identity.** For every `size >= 1` and every `price_bp in [1, 9_999]`:
  `cost_cents(size, price_bp) == cash_out_cents(size * MILLI, price_bp, BINARY_TICK_SIZE_MICRO,
  BINARY_POINT_VALUE_MICRO)` and `proceeds_cents(size, price_bp) == cash_in_cents(...)` likewise, because
  `MILLI * 100 * 1_000_000 // NOTIONAL_DENOMINATOR` is exactly `1 // 100` applied after the product. E2's
  hypothesis test asserts both identities over the full range, so no bp price already written changes
  value (ruling R145). The payout of a binary is `cash_in_cents(size * MILLI, SETTLE_YES_BP, 100,
  1_000_000) == size * 100` cents, which is 8.7's `position * 100`.
- **Why `100` and not the PRD's `10_000`** (ruling R145). PRD v4 1.2 gives a binary `tick_size_micro =
  10_000` with `point_value_micro = 1_000_000`. Ten thousand millionths of a quote unit is one cent, so
  6 327 ticks would be 63.27 USD and forty contracts would cost 2 530.80 USD against section 1.4's 25.31
  USD; the two numbers cannot both hold and the PRD itself defers the formulas to this amendment. One
  basis point of a one-unit payout is `100` micro, which is what the identity above needs and what the
  worked example below shows. The PRD's other three rows are arithmetically right and are kept verbatim.
- **Sizes.** `size_milli` is the one quantity unit of the price model: thousandths of one unit of position
  (a milli-contract, a milli-coin, a milli-share, a milli-lot of one base unit). A **binary** order stays
  in whole contracts everywhere it already is (`MarketAction.size`, `target_position`, `PositionView`,
  the journal) and becomes `size * MILLI` at the liquidity boundary, exactly as 16.1 already does;
  `Execution` truncates a binary fill to whole contracts (16.1). A **continuous** instrument's `size`,
  `target_position` and `position` fields are **in milli-units** wherever the binary ones are in
  contracts, and are not truncated: a fill of 1 milli-coin is a fill (ruling R148). `actions.v2.json` and
  `journal.v2.json` widen those bounds to `SIZE_MILLI_MAX`; the field names do not change.
- **Prices.** `price_ticks` is the one price unit. For a binary, `price_ticks == price_bp`, and every
  `_bp` price field of the journal, the views and the actions carries the instrument's **ticks** for
  every kind: the suffix is the v2 field name, kept so that `filled`, `market_priced`, `order_placed` and
  `MarketAction` are one event and one shape per name (ruling R148), and its unit is one tick, which for a
  binary is one bp. The bounds widen to `1..PRICE_TICKS_MAX` in the schemas; the loader and the runner
  enforce `1..9_999` on a binary, where the schema used to.
- **Overflow** (ruling R147). Every integer the engine **stores** (a journal field, a manifest number, a
  sqlite column, a `results.json` value) fits in `INT63_MAX`; the products it computes on the way need
  not and are not, because Python integers are exact and the product is never written. The caps that
  make the stored side hold: `price_ticks <= PRICE_TICKS_MAX`, `size_milli <= SIZE_MILLI_MAX`, and per
  fill or cash event `notional_micro(...) <= NOTIONAL_CENTS_MAX * NOTIONAL_DENOMINATOR`, which
  `Execution` checks before pricing, with the limit price or the bar's high (8.6, ruling R196), and refuses
  as `order_rejected(bad_size)`; `INT63_MAX` is more than
  nine thousand times `NOTIONAL_CENTS_MAX`, so a run of any length whose fills all pass the check cannot
  overflow a cash, an equity or a PnL column at the bankrolls section 8.1 allows. At the caps the raw
  product reaches `10**45`, which is why the contract says "exact" and not "64-bit": a port to a
  fixed-width language must widen, never reorder the division.

**Worked examples** (`tests/test_contract_schemas.py` executes every number):

| Instrument | `tick_size_micro` | `point_value_micro` | Order | `notional_micro // 10**13` | `cash_out_cents` | `cash_in_cents` |
|---|---|---|---|---|---|---|
| a binary contract (`kalshi-...`), 40 contracts at 63.27 cents | `100` | `1_000_000` | `size_milli = 40_000`, `price_ticks = 6_327` | 2 530.8 | `2_531` (section 1.4's `cost_cents(40, 6_327)`) | `2_530` |
| BTCUSDT on Binance, one milli-coin at 63 412.57 USDT | `10_000` | `1_000_000` | `size_milli = 1`, `price_ticks = 6_341_257` | 6 341.257 | `6_342` | `6_341` |
| ES on CME, two contracts at 5 432.25 (quarter points, 50 USD a point) | `250_000` | `50_000_000` | `size_milli = 2_000`, `price_ticks = 21_729` | 54 322 500 exactly | `54_322_500` (543 225.00 USD) | `54_322_500` |
| EURUSD, 100 000 EUR at 1.08325 (a tenth of a pip) | `10` | `1_000_000` | `size_milli = 100_000_000`, `price_ticks = 108_325` | 10 832 500 exactly | `10_832_500` (108 325.00 USD) | `10_832_500` |

A pip venue quotes EURUSD with `tick_size_micro = 100`; the two scales are two instruments with two ids,
never one instrument read two ways. One ES contract at 10 000 points is `notional_micro = 1_000 *
40_000 * 250_000 * 50_000_000 = 5 * 10**20`, twenty million times under the `NOTIONAL_CENTS_MAX`
check. On ES at 5 432.25 one milli-contract is
27 161.25 cents of notional, so the check fires above `size_milli = 36_817_156_795` (36 817 156
contracts), where the notional first exceeds `10**15` cents; on EURUSD the size cap fires first, because
`SIZE_MILLI_MAX` milli-lots at parity is only `10**11` cents.

### 17.2 Session calendars, the run calendar and tradability

**A bar exists only inside a session** (ruling R149). Every instrument names a `session_calendar_id`;
the calendar is a **dated** record, `src/pmx/schemas/session_calendar.v1.json`, generated by F4
(`pmx.data.sessions`) from the exchange's rules and holidays for the dataset's window and **sealed with
the dataset** at `data/datasets/<name>/calendars/<calendar_id>.json`, inside the walk of 4.3:

```
schema_version "session_calendar.v1", calendar_id, description, source_url, as_of_date,
window {start_ms, end_ms},
sessions [{open_ms, close_ms}]        sorted by open_ms, open_ms < close_ms, non-overlapping, every one
                                      inside the window; the window covers every bar of every instrument
                                      that names the calendar (the loader refuses a bar outside it)
holidays [yyyy-mm-dd]                 informative; the sessions list is the normative object
```

Daylight saving is why the record is dated and not a weekly template: XNYS opens at 13:30Z in summer and
14:30Z in winter, and a template in UTC would be wrong for half the year. A bar `b` of instrument `i`
**exists** iff its interval intersects a session: `in_session(i, b.t_ms) = exists s in sessions with
b.t_ms < s.close_ms and b.t_ms + interval_ms > s.open_ms`. An instrument file that carries a bar with
`in_session == false`, or that lacks a bar at a grid point where `in_session` holds between
`bar_of(listed_at_ms)` and `bar_of(delisted_at_ms)` (or the window end), fails the loader
(`SchemaError`, naming the bar), exactly as 7.2 refuses a gap or a duplicate on a binary; extended hours
are excluded by default and a venue's pre-market bar is therefore a load error, not a feature. **The rule
binds a `ContinuousInstrument` only** (ruling R185): a binary keeps 7.2 verbatim, its file is never checked
against a calendar, and the ninety days of `opened_early_days` before the resolution window stay legal on
it as they always were. The `continuous` calendar is **reserved and synthesised by the loader, never a
file**: one session `[0, INT63_MAX)`, so `Dataset.calendar("continuous")` answers on a dataset with no
`calendars/` directory (the demo pack and the 2026-09-08 build), a crypto instrument's bars are dense from
`bar_of(listed_at_ms)` on, and a binary names it through `Market.instrument` without reading it. A
`calendars/continuous.json` file fails the loader (`SchemaError`) and `session_calendar.v1.json` refuses
the id; `pmx.data.sessions` generates the exchange calendars for a window and the loader reads them.

**The run calendar is the union of the instruments' bar timestamps** (5.3 as generalised, ruling R149).
`Calendar.bars()` (E1) yields every `t` in `[t0_ms, t1_ms)` on the grid at which at least one instrument
of the run has a bar, ascending; a `t` where no instrument has a bar (a weekend of an equity-only run) is
not a bar of the run and produces no event. On a run that carries a binary, every grid point is a bar,
as today. `BarSlice.closing_ids` carries the instruments with `closes(i, t)`, and `Calendar.last_bar`,
`Calendar.next_bar` and `Calendar.prev_bar` (8.3) are the one implementation of the three lookups the table
below and 17.3 need, so E5 and `Execution` read them from E1 and compute none of their own (ruling R187).
The four predicates of 5.3 read, for an instrument `i` at a bar `t` of the run:

| Predicate | Binary (unchanged, 5.3) | Continuous |
|---|---|---|
| `listed(i, t)` | `bar_of(created_at_ms) <= t <= bar_of(resolved_at_ms)` | `bar_of(listed_at_ms) <= t` and (`delisted_at_ms is None` or `t < bar_of(delisted_at_ms)`), where `delisted_at_ms` is read off `Dataset.market(i).instrument` and never off `MarketMeta` (ruling R228) |
| `open(i, t)` (in observations) | `listed and not settled before t` | `listed(i, t) and in_session(i, t)` |
| `tradable(i, t)` (a fill may land) | `listed and t + interval_ms <= close_at_ms and not settles(i, t)` | `open(i, t) and t < last_bar(i)`, where `last_bar(i)` is the last bar of the run at which `open(i, t)` holds; `MarketView.tradable` carries `open(i, t)`, not this predicate, and `MarketView.close_at_ms` is `0`, because both would announce `last_bar(i)` (ruling R181) |
| `actionable(i, t)` (16.2) | `tradable(i, t + interval_ms)` | `tradable(i, t + interval_ms)` where `t + interval_ms` is read as **the next bar of `i`**, not the next grid point |
| `settles(i, t)` | `bar_of(resolved_at_ms) == t` | never; `closes(i, t) = (t == last_bar(i))`, the bar of the forced flat (17.3) |

The latency rule of 16.2 is unchanged: an action decided at `t` executes at the open of the instrument's
next bar, which for a session instrument decided on a Friday afternoon bar is Monday's first bar, and
that gap is the tape's, not the engine's. `pending_market_ids(t_ms)` (8.6) therefore holds an item until
the instrument's next bar arrives, and `Execution` drains it at that bar with `decided_at_ms` naming the
bar it was decided at, the instrument's previous bar (ruling R192: `bar_ms - interval_ms` is the
`continuous` spelling of the same rule); the queue is keyed by instrument, reads `Calendar.next_bar`, and
an item whose instrument never has another bar in the run is `order_rejected(not_tradable)` at the run's
last bar. An instrument with no bar at `t` is simply not open at `t`: no observation entry,
no `forecast_recorded`, no `market_priced`. A ruined agent's carried forecasts (8.2) are recorded on the
bars the instrument is open at and no others.

The `Dataset` of 7.2 gains the continuous instruments behind the same names: `metas` carries one
`MarketMeta` per instrument of every kind with `kind` on it (`MarketMeta.kind`, ruling R144),
`market(market_id)` returns a `Market` or a `ContinuousInstrument` (both satisfy `Instrument`; a continuous
one clipped at `validation_end_ms`, ruling R182), and `Dataset.calendar(calendar_id)` returns the sealed
`SessionCalendar`, or the synthesised `continuous` one. `SessionCalendar` is a `pmx.types` dataclass (D1)
and `in_session`, `next_bar_ms` and `load_calendar` live in `pmx.data.sessions`, **D1's file, applied by
gate G2** (ruling R174), so E1's `Calendar`, E2's `Execution` (which receives the run's calendars through
its `calendars` argument, 8.6) and the loader import one implementation in wave 2 rather than waiting for
wave 3b. `BuildConfig.kinds` (7.4) selects
which kinds a build imports, and `RunConfig.kinds` (8.1) which kinds a run carries, empty meaning every
kind the dataset has.

### 17.3 `CashEvent`: funding, dividends, splits, rolls, borrow fees and the forced flat

**One dated record family, applied by execution in the settle phase, journaled once** (ruling R151). A
`CashEvent` is `pmx.types.CashEvent`, serialised by `src/pmx/schemas/cash_event.v1.json`:

```python
CASH_EVENT_KINDS = ("funding", "dividend", "split", "roll", "borrow_fee", "carry", "forced_flat")
DATA_CASH_EVENT_KINDS = CASH_EVENT_KINDS[:4]       # what an instrument file may carry; the other three are the engine's (R177)

@dataclass(frozen=True, slots=True)
class CashEvent:
    cash_event_id: str        # "ce-" + sha256(canonical_json([market_id, kind, t_ms, detail]))[:16]
    market_id: str            # the instrument
    kind: str                 # one of CASH_EVENT_KINDS
    t_ms: int                 # the venue's instant: the OPEN of the first bar priced in the new regime for
                              # dividend, split and roll (R175); the last instant of the applying bar for an
                              # engine event (R176); the funding time for funding
    origin: str               # "data" for the first four kinds, "engine" for borrow_fee, carry and forced_flat
    source_url: str           # "" for an engine event
    detail: Mapping[str, int | str]    # the kind's fields below, integers and strings only

# Ruling R175: the bar at whose settle phase execution applies the event. One body, in pmx.engine.calendar,
# re-exported by pmx.engine.execution under this name and called by the observation path for R183 (ruling R204).
def applies_at(event: CashEvent, instrument: Instrument, calendar: BarLookups | None) -> int | None:
    bar = bar_of(event.t_ms, instrument.interval_min)
    if event.kind in OLD_REGIME_KINDS:                  # ("dividend", "split", "roll"), pmx.engine.calendar
        if calendar is None:
            return None                                 # no calendar to read prev_bar from: not applied, never visible
        return calendar.prev_bar(instrument.id, bar)   # the last bar priced in the OLD regime; None: not applied
    return bar                                          # funding, borrow_fee, carry, forced_flat
```

| Kind | Applies to | `detail` | What execution does for an agent with `position_milli = q != 0` (nothing for `q == 0`) |
|---|---|---|---|
| `funding` | `perp` | `rate_ppm: int` (signed; the venue's published rate for that funding time), `mark_ticks: int` (the venue's mark at the funding time, else the bar's close) | `paid_micro = notional_micro(abs(q), mark_ticks, tick, point) * rate_ppm`; a long pays when `rate_ppm > 0` and a short receives: `cash_delta_cents = -cash_out(...)` when the agent pays (`-((-abs(paid_micro)) // (NOTIONAL_DENOMINATOR * PPM_ONE))`) and `+cash_in(...)` when it receives (`abs(paid_micro) // (NOTIONAL_DENOMINATOR * PPM_ONE)`); position unchanged |
| `dividend` | `equity` | `dividend_micro: int` (per unit, in millionths of the quote currency); `t_ms` is the first instant of the ex-date and the event applies at the cum-date close, the bar before `bar_of(t_ms)` (ruling R175) | a long receives `q * dividend_micro // (MILLI * MICRO // CENTS_PER_UNIT)`, a short pays the ceiling of the same magnitude; position unchanged |
| `split` | `equity` | `numerator: int >= 1`, `denominator: int >= 1` (a 4-for-1 split is `4, 1`; a 1-for-10 reverse split is `1, 10`) | `position_after = split_position_milli(q, numerator, denominator) = sign(q) * round_half_up(abs(q) * numerator, denominator)`; `avg_cost_ticks_after = round_half_up(avg_cost_ticks * denominator, numerator)`; `cash_delta_cents = 0` (cash in lieu is not modelled; the rounding is at most half a milli-unit and is stated so nobody "fixes" it); every resting order on the instrument is expired with `reason = "corporate_action"` because its price is in the old scale (ruling R153); `t_ms` is the first instant of the effective date and the event applies at the last pre-split bar (ruling R175) |
| `roll` | `future` | `from_symbol`, `to_symbol`, `from_price_ticks`, `to_price_ticks`, `gap_ticks = to - from` | two **event fills** (ruling R152): a `filled` that closes `q` at `from_price_ticks` and a `filled` that reopens `q` at `to_price_ticks`, each with its taker `fee_charged`, each with `order_placed(origin="roll")`, all in the settle phase; `avg_cost_ticks_after = to_price_ticks`; resting orders expire with `reason = "roll"`. The gap is recorded in `detail` and in the raw series and is **never traded through**: a position never earns or loses the gap, it pays two fills. `t_ms` is the first instant of the first new-contract bar and the event applies at the last old-contract bar (ruling R175); the reopening leg goes through `truncate_for_cash` and the short-notional rule below, so a position can shrink across a roll, and the residual is in that leg's `unfilled_size` and `unfilled_reason` and in `position_after` (ruling R198) |
| `borrow_fee` | `equity` with `q < 0` | `rate_ppm_per_day: int` (from the borrow schedule of 17.4), `days: int` (calendar days since the previous session close, so a weekend is charged on Monday), `mark_ticks` | pays `-((-(notional_micro(abs(q), mark_ticks, tick, point) * rate_ppm_per_day * days)) // (NOTIONAL_DENOMINATOR * PPM_ONE))` at the settle phase of the last bar of every session, with `t_ms = that bar + interval_ms - 1`, the bar's last instant, so `bar_of(t_ms)` is the applying bar (ruling R176); the engine generates one event per (instrument, session) from the `calendars` it was constructed with (8.6, ruling R174) and it exists only for agents who are short |
| `carry` | `fx` with a `carry_schedule_id`, `q != 0` | `rate_ppm_per_day: int` (signed, the carry schedule's rate of 17.4), `days: int` (calendar days since the previous session close), `mark_ticks` (the bar's close) | `paid_micro = notional_micro(abs(q), mark_ticks, tick, point) * rate_ppm_per_day * days`; a long **receives** when `rate_ppm_per_day > 0` and pays when it is negative, a short the reverse, each side rounded against the agent exactly as `funding` is; at the settle phase of the last bar of every session with `t_ms = that bar + interval_ms - 1`; `origin = "engine"`, one event per (instrument, session), only for agents with a position (ruling R177: an engine-generated event cannot be a data kind, and the importer may not read `pmx.engine.fees`) |
| `forced_flat` | every continuous kind | `reason: "window_end" \| "delisted"`, `price_ticks` (the close of `last_bar(i)`); `t_ms = last_bar(i) + interval_ms - 1`, the bar's last instant, so `bar_of(t_ms) == last_bar(i)` and the id hashes that instant (ruling R176) | one **event fill** (ruling R150) that closes `q` at `price_ticks`, taker fee, `order_placed(origin="forced_flat")`, `filled(price_source="event")`; a cover that cash cannot pay is truncated by `truncate_for_cash` like any buy and the residual is journaled as `position_after != 0` (ruling R154) |

**Entitlement follows the regime of the prices** (ruling R175). A `dividend`, a `split` and a `roll` are
applied to the position held at the close of the last bar whose prices are in the old regime: the cum-date
close, the last pre-split bar, the last old-contract bar, which is `prev_bar(i, bar_of(t_ms))` above. The
raw tape reflects the event from the open of `bar_of(t_ms)` (the ex-date open is lower by the dividend, the
effective-date open is in the new scale, the first new-contract bar prints the new contract), so an order
decided the bar before fills at those prices in the execute phase and must be owed nothing at the settle
phase: a buy at the ex-date open receives no dividend, a buy at the split's effective open is not
multiplied, and a roll nets nothing against fills made at new-contract prices. The importer stamps the
**open of the first bar priced in the new regime** (a grid point of the instrument: the ex-date bar, the
effective-date bar, the first bar whose prints are the new contract's), never an intraday instant, and the
engine derives the application bar from it; the schema test asserts the three fixture events sit on a bar
open. `funding`, `borrow_fee`, `carry` and `forced_flat` are charges on, or the
close of, the position held through an instant and apply at `bar_of(t_ms)`. An event whose application bar
is not a bar of the run (a roll dated on the run's first bar of the instrument, whose previous bar lies
outside it) is not applied, because no position can exist before the run's first bar. E2's tests carry the
two buy cases.

Ordering inside the settle phase of bar `t`: binary settlements first (8.2 step 5, unchanged), then for
each continuous instrument in canonical order, its cash events with `applies_at(e) == t` in `(kind order as
in CASH_EVENT_KINDS, t_ms, cash_event_id)` order (ruling R193: kind first, so two events of one bar apply in
kind order whatever their stamps, and a funding event never applies after a roll of the same bar), and for each event the agents in
`agent_id` order. `forced_flat` is last in `CASH_EVENT_KINDS` and therefore last on its bar. A `split` on
the same bar as a `dividend` applies after it (the ex-date dividend is per pre-split share, which is how
venues publish it).

**Event fills are execution's, priced by `pmx.engine.liquidity.event_fill`** (ruling R152), so
architecture rule 9 holds: `event_fill(order: LiquidityOrder, *, price_ticks: int, schedule: FeeSchedule)
-> Fill` returns a `Fill` with `price_bp = base_price_bp = price_ticks`, `slippage_bp = 0`,
`filled_milli = order.size_milli`, `unfilled_reason = "none"`, `price_source = "event"`, `role =
"taker"` and the schedule's fee, and it is the only path that may emit `price_source = "event"`. The
envelope rule of 16.1 is satisfied by construction (`price_ticks` is a printed price of the tape: the
roll record's two prices, or the bar's close) and `check_envelope` does not drive it, because it is not
a `LiquidityModel`. A roll's two fills and the forced flat are the three places a `filled`,
`order_placed` or `fee_charged` event carries `phase = "settle"`; everywhere else the three stay in
`execute`.

**Shorts on a continuous instrument** (ruling R154). `position_milli < 0` is a short of `abs(q)` units,
legal only where `short_allowed` is true. Netting is 8.5's with the NO-leg arithmetic replaced by the
liability model: a `sell` of `s` with `q >= 0` first closes `min(s, q)` receiving `cash_in_cents`, then
opens `s - min(s, q)` short **receiving** `cash_in_cents` at the fill price; a `buy` with `q < 0` first
covers `min(s, -q)` **paying** `cash_out_cents`, then opens long. The opening notional of a short may not
exceed the agent's free cash at the fill (`short_notional <= free_cash`, `unfilled_reason = "cash"`
beyond it), so that a cover up to a doubling of the price is always affordable; beyond that the cover is
truncated for cash, the residual short is carried and marked as a liability, equity falls below the ruin
floor and 8.7 freezes the agent. A fill never takes cash below zero; a debit cash event can (below); equity
can. A binary's NO leg keeps 8.5 exactly, because a NO contract is a long in the complement and pays
`cost_cents(s, 10_000 - p)` up front.

**A debit balance** (ruling R179). `funding`, `dividend`, `borrow_fee` and `carry` subtract
`cash_delta_cents` from an agent who may have spent the cash a short brought in on other instruments, and
no truncation applies to a charge the venue would have collected: cash may fall below zero. While
`cash_cents(a) < 0` the agent carries a debit balance: `free_cash` is `0`, so no opening fill lands
(`unfilled_reason = "cash"`); closing fills and credits repay it; and ruin stays 8.7's rule on equity,
which the debit lowers cent for cent. The expiry is triggered by the reservation and not by the sign of
cash (ruling R215, one sentence with 8.9's invariant line): **the cash event that leaves
`reserved_cents(a)` above `max(0, cash_cents(a))` expires every resting order of the agent with
`reason = "debit"`**, which includes every event that takes cash below zero, so `reserved_cents(a) == 0`
while cash is negative and a debit that leaves cash positive yet under the reservations fires the same
expiry instead of leaving a reservation unfunded. The shortfall is not a separate liability field:
`equity_marked.cash_cents` and `PortfolioView.cash_cents` are signed and `equity = cash + positions_value`
holds unchanged. E2's cases include a dividend debit on a short whose cash was spent elsewhere.

**The forced flat at the window end** (ruling R150). At the settle phase of `last_bar(i)`, the
instrument's last bar in the run: `min(bar_of(delisted_at_ms) - interval_ms, the run's last grid bar)`
when `Dataset.market(i).instrument.delisted_at_ms` is set (the bar **before** the one that contains the
delisting instant) and the run's last grid bar when it is `None`, read off the record and never off
`MarketMeta.resolved_at_ms` (ruling R228). At that bar every non-zero position is closed by an engine
order at the bar's close and the runner emits `instrument_closed`. The flat is a **fill** and never a
mark: a mark would let a run end with a paper number nobody could have realised, and a fill pays the fee the venue would have
charged. A run whose `t1_ms` falls inside the dataset's window therefore ends flat on every continuous
instrument, and a claim on the sealed fold cannot carry an open position across its edge. Section 8.7's
"positions ride to settlement" is the binary row of this rule; a continuous instrument has nothing to
ride to.

**The accounting invariant across kinds** (8.9 as generalised, ruling R151). For every agent `a`, at
every bar close and at run end, over the journal alone:

```
cash_cents(a)     == bankroll_cents + sum(filled.cash_delta_cents)  - sum(fee_charged.fee_cents)
                                    + sum(settlement_applied.cash_delta_cents)
                                    + sum(cash_event_applied.cash_delta_cents)                   (all for a)
cash_cents(a)     >= 0 unless the last event that moved it is a cash_event_applied debit (ruling R179)
reserved_cents(a) == sum(order_placed.reserved_cents) - sum(filled.released_cents) - sum(order_expired.released_cents)
reserved_cents(a) <= max(0, cash_cents(a));  reserved_cents(a) == 0 while cash_cents(a) < 0 and at run end
position(a, i)    == the last position_after written for (a, i) by a filled or a cash_event_applied, where
                     every filled satisfies position_after - position_before == its signed filled size,
                     cash_event_applied(kind="split") satisfies position_after == split_position_milli(position_before, ...),
                     cash_event_applied(kind in roll, forced_flat) satisfies position_after == the position_after of
                     the last filled in its order_ids (position_before is the position before the first), and
                     cash_event_applied(kind in funding, dividend, borrow_fee, carry) satisfies
                     position_after == position_before (ruling R178)
position(a, i)    == 0 after settlement (binary) and after instrument_closed (continuous) unless the forced flat
                     reports unfilled_reason == "cash", in which case equity_marked carries the liability
positions_value_cents(a) == sum over open positions of mark_value_cents(position, close_ticks of bar t, tick, point)
                     for a continuous instrument, and 8.7's YES and NO values for a binary; signed
equity_cents(a)   == cash_cents(a) + positions_value_cents(a)
```

| Kind | Lines that can be non-zero beyond fills, fees and reservations |
|---|---|
| `binary` | `settlement_applied.cash_delta_cents`; positions flat after settlement |
| `spot_crypto` | `forced_flat` fill and fee at `last_bar` |
| `perp` | `cash_event_applied(funding)` at every funding time; `forced_flat` |
| `fx` | `cash_event_applied(carry)` at every session close, only when the instrument names a carry schedule (17.4; off by default, ruling R177); `forced_flat` |
| `equity` | `dividend`, `split` (position only), `borrow_fee` (shorts only); `forced_flat` |
| `future` | `roll`: two fills and two fees per roll; `forced_flat` |

E2's hypothesis tests generate 1 000 sequences per kind, including a funding sign flip, a reverse split
on a short, a roll with a negative gap, a roll with a positive gap on an agent with no free cash (R198), a
dividend on a short, a dividend debit that takes cash below zero (R179), a buy at an ex-date open that
receives no dividend and a buy at a split's effective open that is not multiplied (R175), a carry on a long
at a negative rate (R177), and a forced flat that cash cannot pay, and assert every line; E2E-1b (PRD v4 section 7) asserts them on the mixed fixture and replays it to an
identical hash (AC-22).

**What the journal records** (9.2 as generalised; the rows are in the catalogue, the widenings in
`journal.v2.json`):

| Event | Phase | Per | Payload |
|---|---|---|---|
| `cash_event_applied` | settle | (agent, instrument, cash event) with `position != 0` before or after | `agent_id`, `market_id`, `cash_event_id`, `kind`, `origin`, `position_before`, `position_after` (before the first and after the last event fill for `roll` and `forced_flat`, ruling R178), `avg_cost_ticks_before`, `avg_cost_ticks_after`, `cash_delta_cents: int` (`0` for `split`, `roll` and `forced_flat`, whose money moves in their `filled` and `fee_charged` events), `order_ids: list[str]` (the event fills, else `[]`), `detail: object` (the kind's fields) |
| `instrument_closed` | settle | continuous instrument, once, at `last_bar(i)` | `market_id`, `kind`, `reason: "window_end"\|"delisted"`, `last_price_ticks`, `n_bars` (bars of the instrument inside the run), `n_forecasts_unresolved` (horizon forecasts whose horizon lies beyond the run) |

`market_listed` gains `kind`, `vendor`, `symbol`, `tick_size_micro`, `point_value_micro`,
`session_calendar_id`, `borrow_schedule_id` and `carry_schedule_id`, **declared but not yet required**
in `journal.v2.json` for ruling R129's reason: `pmx.journal`'s dataclasses are D7's and the shipped
backtest fixture is a binary journal; the projection reads `binary`, the provider, `100`, `1_000_000`,
`"continuous"` and `null` when they are absent (ruling R164), and gate G2 promotes them with
`decided_at_ms`. `order_placed.origin` gains `roll` and `forced_flat`; `order_expired.reason` gains
`corporate_action`, `roll` and `delisted`; `filled.price_source` gains `event`; the three execute-phase
events accept `phase = "settle"` for event fills once gate G2 widens their `PHASES` and the schema's
enum together (the two new event rows above enter `oneOf` in the same commit, ruling R164);
`equity_marked.positions_value_cents` becomes a signed integer. `settled` and `settlement_applied` stay binary-only and are never emitted for a continuous
instrument; `realised_pnl_cents` for a continuous (agent, instrument) is `sum(filled.cash_delta_cents) -
sum(fee_charged.fee_cents) + sum(cash_event_applied.cash_delta_cents)` over it, and is what
`PerMarket.realised_pnl_cents` (12.11) carries for every kind.

**Visibility** (ruling R183, which replaces R151's blanket ban by the as-of rule every other datum obeys).
A `CashEvent` is visible exactly as a bar is: once its application bar has completed (`applies_at(e) +
interval_ms <= now_ms`) it is the venue's published past and appears in `MarketView.cash_events` as a
`CashEventView(kind, t_ms, applied_at_ms, detail)`, the last `CASH_EVENTS_VIEW_MAX = 30` **data** events of
the instrument (engine events are the agent's own and reach it through its portfolio); before that it never
appears in an observation, a prompt or a research result, so an announced dividend is hidden until the
cum-date close and a funding time until it is paid. Its cash effect reaches the agent as any fill does, in
the portfolio of the next bar. A feature may read the **venue's fixed schedule** (funding every eight hours,
the exchange's session calendar) because that is the venue's rule and not a datum about the future; R3a's
`hours_to_funding` and `session_minute` are legal. 7.9's list carries the unapplied events with
`cash_event_id`, `rate_ppm`, `dividend_micro`, `gap_ticks` and every `detail` key, and E1's poisoned-future
test injects one event whose application bar has not completed and asserts it does not surface, and one
that has and asserts it does. Without this rule the `carry` family of 17.7 had no rate to read.

### 17.4 Fee, borrow and carry schedules as data, and the half-spread floor

**`FeeSchedule` gains `kind` and `model`** (8.8 as generalised, ruling R155). Every schedule is data
shipped in `pmx.engine.fees.FEE_SCHEDULES` (E2) with a `source_url` and an `as_of_date`, and the market's
or instrument's `fee_schedule_id` names one:

```python
FEE_MODELS = ("pq_permille", "notional_bp", "per_contract", "zero")

@dataclass(frozen=True, slots=True)
class FeeSchedule:
    schedule_id: str; provider: str; kind: str; model: str
    taker_permille: int = 0; maker_permille: int = 0            # pq_permille: 8.8's binary rule, unchanged
    taker_bp: int = 0; maker_bp: int = 0                        # notional_bp: bp of the notional cents
    sale_bp: int = 0                                            # notional_bp: charged on sells only (the SEC fee)
    per_contract_cents: int = 0; exchange_cents: int = 0        # per_contract: per whole contract per side
    min_half_spread_ticks: int = 0                              # the floor of 16.1 rule 1 when no quote is known
    rounding: str = "ceil"
    source_url: str = ""; as_of_date: str = ""; note: str = ""

def fee_cents(schedule: FeeSchedule, *, size: int, price_bp: int, role: str,
              side: str = "buy", tick_size_micro: int = BINARY_TICK_SIZE_MICRO,
              point_value_micro: int = BINARY_POINT_VALUE_MICRO) -> int: ...
```

`fee_cents` keeps its 8.8 body for `pq_permille` (`size` in contracts, `price_bp` in bp) and extends by
keyword-only defaults (preamble rule 2) for the other models, where `size` is `size_milli`: `notional_bp`
is `-((-(notional_micro * bp)) // (NOTIONAL_DENOMINATOR * BP_ONE))` with `bp = taker_bp` or `maker_bp`
plus `sale_bp` when `side == "sell"`; `per_contract` is `-((-(size_milli * (per_contract_cents +
exchange_cents))) // MILLI)`; `zero` is `0`. Every fee rounds up, once (rule 5 of 16.1 holds over the
fill the journal writes, unchanged). Shipped schedules (E2 ships the binary five of 8.8 and these; F1 and
F2 may add a venue's tier by adding a row, never by changing a formula):

| `schedule_id` | provider | kind | model | numbers | source | as of |
|---|---|---|---|---|---|---|
| `binance-spot-2026-09` | binance | spot_crypto | notional_bp | taker `10`, maker `10` | `https://www.binance.com/en/fee/schedule` | `2026-09-08` |
| `binance-perp-2026-09` | binance | perp | notional_bp | taker `5`, maker `2` | `https://www.binance.com/en/fee/futureFee` | `2026-09-08` |
| `bybit-perp-2026-09` | bybit | perp | notional_bp | taker `5`, maker `2` | `https://www.bybit.com/en/help-center/article/Trading-Fee-Structure` | `2026-09-08` |
| `kraken-spot-2026-09` | kraken | spot_crypto | notional_bp | taker `26`, maker `16` | `https://www.kraken.com/features/fee-schedule` | `2026-09-08` |
| `coinbase-spot-2026-09` | coinbase | spot_crypto | notional_bp | taker `60`, maker `40` | `https://www.coinbase.com/advanced-fees` | `2026-09-08` |
| `xnys-zero-2026-09`, `xnas-zero-2026-09`, `arcx-zero-2026-09` | xnys, xnas, arcx: one `FeeSchedule` row per provider with the same numbers, because `FeeSchedule.provider` is one provider and an instrument's `provider` names the venue whose schedule applies (ruling R197) | equity | notional_bp | taker `0`, maker `0`, sale `0` (the SEC section 31 rate is published per fiscal year and E2 reads it into `sale_bp`), `min_half_spread_ticks = 1` | `https://www.sec.gov/divisions/marketreg/mrfreqreq.shtml` | `2026-09-08` |
| `cme-es-2026-09` | xcme | future | per_contract | `per_contract_cents = 125`, `exchange_cents = 128` (round turn halved per side) | `https://www.cmegroup.com/company/clearing-fees.html` | `2026-09-08` |
| `otcfx-spread-2026-09` | otcfx | fx | zero | `min_half_spread_ticks = 5` (half a pip at a tenth-of-a-pip tick, the retail floor) | `https://www.bis.org/statistics/rpfx22.htm` | `2026-09-08` |

The numbers are what the pages showed on the date; F1 and F2, the packages that may open a socket (ruling
R216), re-read each page, correct a number that moved and record the correction in the row, exactly as D2
does for the Kalshi PDF of 8.8; until then the rows stand with their `as_of_date` and the three equity rows
keep `sale_bp = 0` with the reason in their note. A row is never a formula.

**Borrow and carry schedules are the same record family** with the rate in `detail` fields of their own:

```python
@dataclass(frozen=True, slots=True)
class CarrySchedule:                  # pmx.engine.fees.CARRY_SCHEDULES (E2); named by borrow_schedule_id or carry_schedule_id
    schedule_id: str; provider: str; kind: str
    role: str                         # "borrow" (equity shorts) | "carry" (fx swap)
    rate_ppm_per_day: int             # signed for carry (long pays when negative), >= 0 for borrow
    source_url: str; as_of_date: str; note: str
```

`xnys-borrowgc-2026-09`, `xnas-borrowgc-2026-09` and `arcx-borrowgc-2026-09` (`borrow`, `rate_ppm_per_day
= 8`, about 0.3 percent a year, the general-collateral floor, one row per provider for R197's reason; a
hard-to-borrow list is a later row) are the borrow schedules shipped, and no carry schedule ships: an `fx`
instrument's `carry_schedule_id` is `null` unless a dataset declares the rate-differential approximation of
PRD v4 1.1, which is **off by default** and, when on, is applied as the engine-origin `carry` cash event of
17.3 at the last bar of every session (ruling R177), computed from the named `CarrySchedule` exactly as
`borrow_fee` is from its borrow schedule and signed: a long receives a positive `rate_ppm_per_day` and pays
a negative one. The kind table of 17.1 and the manifest's `schedules` block (17.9) say which schedules a
dataset used.

**The half-spread floor when no quote is known** (16.1 rule 1 generalised, ruling R156). A crypto or
Yahoo bar carries no bid and no ask. Rule 1 of the envelope is then not "unconstrained": the base of a
market order is `open_ticks + half_spread_ticks` for a buy and `open_ticks - half_spread_ticks` for a
sell, with

```python
def half_spread_ticks(bar_prev: Bar, bar: Bar, *, schedule: FeeSchedule) -> int:
    """Corwin and Schultz (2012) on two consecutive bars' highs and lows, then the schedule's floor.

    Bar is 7.2's one in-memory bar (ruling R173); its _bp fields carry ticks on a continuous instrument."""
    with localcontext() as ctx:
        ctx.prec = 40
        h1, l1, h2, l2 = (Decimal(x) for x in (bar_prev.high_bp, bar_prev.low_bp, bar.high_bp, bar.low_bp))
        beta = (h1 / l1).ln() ** 2 + (h2 / l2).ln() ** 2
        gamma = (max(h1, h2) / min(l1, l2)).ln() ** 2
        k = Decimal(3) - Decimal(2) * Decimal(2).sqrt()
        alpha = ((Decimal(2) * beta).sqrt() - beta.sqrt()) / k - (gamma / k).sqrt()
        estimate = 0
        if alpha > 0:
            spread = Decimal(2) * (alpha.exp() - 1) / (1 + alpha.exp())          # relative spread
            estimate = int((spread * Decimal(bar.open_bp) / 2).to_integral_value(rounding=ROUND_HALF_UP))
    return max(estimate, schedule.min_half_spread_ticks)
```

`Decimal` is the one legal non-integer arithmetic of section 1.3 and the same argument applies: `ln`,
`sqrt` and `exp` are correctly rounded by the decimal specification, so the estimate is the same on every
platform, and the result is an integer number of ticks before anything is priced. A negative `alpha`
(two trending bars) estimates zero and the floor applies; a pair of flat bars estimates zero. Worked
value pinned by the test: bars `(6_360_000, 6_300_000)` and `(6_350_000, 6_310_000)` opening at
`6_330_000` estimate `14_619` ticks. `historical` reads the previous bar of the same instrument (the
last completed one, which is public at the execution bar's open) and applies the floor for the first bar
of an instrument's life. The estimate is the **floor** of the envelope, not its ceiling: rule 3 still
bounds the fill by the bar's range, and a `calibrated_impact` or `adversarial_mm` model may widen it.
For a bar that carries quotes nothing changes. A binary bar without a quote falls under the same rule
with `min_half_spread_ticks = 0` on every binary schedule of 8.8: a Kalshi bar whose candlestick shows a
range is charged the spread that range implies, and a `reconstructed` bar of the demo pack, where every
bar is flat (`open = high = low = close`), estimates zero on every pair, so the demo pack prices at the
open exactly as before and E2's test pins it. 8.6 step 3 is amended in place to say the same.

### 17.5 The forecast record across kinds: horizons, the random walk, the directional Brier and the pinball loss

**Binary kinds keep `prob_ppm` as today.** Every rule of 12.1 and 12.2 is the `binary` row of this
subsection and nothing about a binary forecast, its Brier, its log score, its horizon buckets or its
calibration changes.

**A continuous forecast is per declared horizon** (ruling R157). `RunConfig.horizons_bars: tuple[int,
...] = ()` names the horizons in **bars of the instrument's own bar sequence** (17.2), empty meaning
`default_horizons_bars(interval_min)`, which is `(1, MS_PER_DAY // interval_ms, 7 * MS_PER_DAY //
interval_ms)` with duplicates removed and ascending: `(1, 7)` on a daily grid, `(1, 24, 168)` on an hourly
one. For each open continuous instrument and each declared horizon `h` an agent states:

```python
QUANTILE_LEVELS_PPM = (100_000, 250_000, 500_000, 750_000, 900_000)   # the five levels, fixed

@dataclass(frozen=True, slots=True)
class HorizonForecast:
    market_id: str
    horizon_bars: int                        # one of config.horizons_bars
    up_probability_ppm: int                  # P(price at the horizon > the reference price), 0..PPM_ONE
    quantiles_ticks: tuple[int, ...] | None  # five prices at QUANTILE_LEVELS_PPM, non-decreasing, or None
```

`Actions` gains `horizon_forecasts: tuple[HorizonForecast, ...]` (`actions.v2.json` gains the optional
top-level array; a scripted binary family sends `()`); one per `(market_id, horizon_bars)`, a duplicate
is `action_rejected(duplicate)` with the first occurrence winning, a horizon outside the config is
`action_rejected(bad_horizon)`, a non-monotone quantile tuple is `action_rejected(bad_quantiles)`. A
missing pair is **carried**: the agent's previous statement on that pair, or the random walk below when
none exists, with one exception (ruling R184): when the agent sent a `MarketAction` on the instrument and
no pair for `(market_id, shortest horizon)`, the runner **synthesises** that pair from
`MarketAction.prob_ppm` with `quantiles_ticks = None`, so `trend`, `revert`, `breakout`, `volume` and every
family that states only `prob_ppm` states a direction instead of being rejected on every bar.
`MarketAction.prob_ppm` on a continuous instrument **is** `up_probability_ppm` at the shortest declared
horizon, so every consumer of `prob_ppm` (the hive, `calibrator`, the stacker, the memory ledger) works on
a continuous instrument with no second code path; a pair that **is** present for the shortest horizon must
equal `prob_ppm`, else `action_rejected(bad_prob)`.

**The reference and the realisation.** The reference price of a forecast made at bar `t` is
`price_ref_ticks = MarketView.last_price_bp` at `t`, the close of the last completed bar (5.4), and the
realisation at horizon `h` is the close of the `h`-th completed bar after that reference bar, which is the
close of the bar `h - 1` bars after `t` on the instrument's sequence and becomes public at the open of
the bar `h` bars after `t`, call it `t_h`. `realised_sign = sign(price_realised_ticks -
price_ref_ticks)`, in `{-1, 0, 1}`.

**The random-walk baseline** (ruling R158): `up_probability_ppm = RANDOM_WALK_UP_PPM = 500_000` and
every quantile equal to `price_ref_ticks`. It is the efficient-market statement for a price series and it
is what a missing statement carries. The `random_walk` family (A1, 17.7) states exactly this on every
instrument and every horizon and trades nothing; **its skill is zero by construction** on every
continuous instrument, at every horizon, on every fold, because the skill of an agent is defined as the
baseline's loss minus the agent's loss and the baseline **is** this agent, exactly as
`skill(market_follower) == 0` holds on binaries (12.1, decision D-12). AC-23 states it and E3 asserts it.

**The two losses, in integer micro-units** (ruling R159):

```python
RANDOM_WALK_BRIER_MICRO = 250_000

def directional_brier_micro(up_ppm: int, realised_sign: int) -> int:
    if realised_sign > 0:  return brier_micro(up_ppm, 1)
    if realised_sign < 0:  return brier_micro(up_ppm, 0)
    return (brier_micro(up_ppm, 1) + brier_micro(up_ppm, 0)) // 2      # a flat return: half each way

def pinball_micro(quantiles_ticks: Sequence[int], realised_ticks: int, price_ref_ticks: int) -> int:
    total = 0                                                          # in ticks * ppm, exact
    for level_ppm, q in zip(QUANTILE_LEVELS_PPM, quantiles_ticks, strict=True):
        total += level_ppm * max(0, realised_ticks - q) + (PPM_ONE - level_ppm) * max(0, q - realised_ticks)
    return round_half_up(total, len(QUANTILE_LEVELS_PPM) * price_ref_ticks)   # micro-units of the reference price

def directional_skill_micro(agent_brier_micro: int) -> int:  return RANDOM_WALK_BRIER_MICRO - agent_brier_micro
def pinball_skill_micro(baseline_pinball_micro: int, agent_pinball_micro: int) -> int:  return baseline_pinball_micro - agent_pinball_micro
```

The flat-return rule makes the baseline score `250_000` whatever happens (`brier_micro(500_000, 1) ==
brier_micro(500_000, 0) == 250_000`), so `directional_skill_micro` is `0` for the random walk on every
outcome and every tie, and a directional forecast is not rewarded for a price that did not move.
`pinball_micro` is relative to the reference price so instruments quoted in different units pool: a
one-tick error on ES and a one-tick error on EURUSD are not the same mistake, a one-permille error is.
The baseline's pinball is `pinball_micro((ref,) * 5, realised, ref)`, generally positive, and
`pinball_skill_micro` is baseline minus agent, `0` for the random walk identically. An agent that states
no quantiles has `pinball_micro = None` in its record and `n_quantile_forecasts = 0` in its row; it is
scored on direction only and says so. Worked values pinned by the schema test: the fixture's one-bar
quantiles `(6_300_000, 6_325_000, 6_341_257, 6_356_000, 6_380_000)` against a realisation of
`6_352_010` on a reference of `6_341_257` score `pinball_micro = 666`, the baseline scores `848`, so
`pinball_skill_micro = 182`; a `700_000` up-probability scores `90_000` on an up move, `490_000` on a
down move and `290_000` on a flat return.

**Time weighting and the per-instrument score.** For an agent on a continuous instrument at horizon `h`,
over the forecast bars `t_1 < ... < t_n` whose horizon resolved inside the run:
`dir_brier_micro(a, i, h) = round_half_up(sum(directional_brier_micro_k), n)`, the **plain mean**: forecast
bars are weighted equally and the session gap (a Friday-to-Monday `w_i` of sixty hours under 12.1's
weights) is the tape's, not a weight on the forecast (ruling R191: the rule is stated as a rule, and 12.1's
weighted mean is not invoked because on a session instrument it would not coincide with it), likewise
`pinball_micro(a, i, h)`; `skill_micro(a, i, h) = RANDOM_WALK_BRIER_MICRO -
dir_brier_micro(a, i, h)`; the horizon buckets of 12.1 are replaced by the declared horizons themselves
(`HorizonBucket.bucket` carries `f"h{h}"`, ruling R161); the log score is not defined for a continuous
kind and its column reads `0` with `n: 0`. PMV at horizon `h` (12.1) is `sign(up_ppm - 500_000) *
(price_realised - price_ref)` in ticks, with `bp_ratio` against `price_ref` for a relative number.

**Horizon resolution events** (9.2 as generalised, ruling R160). At the settle phase of bar `t_h` the
runner emits, per `(agent, instrument, forecast bar, horizon)`, in agent then instrument then forecast
bar then horizon order:

| Event | Phase | Per | Payload |
|---|---|---|---|
| `forecast_resolved` | settle | (agent, instrument, forecast bar, horizon) at `t_h` | `agent_id`, `market_id`, `forecast_bar_ms`, `horizon_bars`, `up_probability_ppm`, `quantiles_ticks: list[int]\|null`, `price_ref_ticks`, `price_realised_ticks`, `realised_sign: -1\|0\|1`, `directional_brier_micro`, `pinball_micro: int\|null`, `baseline_pinball_micro`, `carried: bool` |

`baseline_brier_micro` is not a field because it is the constant `RANDOM_WALK_BRIER_MICRO`;
`baseline_pinball_micro` is, because it depends on the realisation. A carried statement resolves like a
stated one (`carried = true`), as a carried `forecast_recorded` scores on a binary; a horizon that lies
beyond the run's last bar of the instrument never resolves, is counted in
`instrument_closed.n_forecasts_unresolved`, and is not scored. `forecast_recorded` gains the optional
`horizons: list[{horizon_bars, up_probability_ppm, quantiles_ticks}]` and `price_ref_ticks` payload
fields (absent on a binary), so the projection rebuilds every continuous score from the journal alone.

**Hive visibility, one bar after the horizon** (mirroring R12, ruling R160). A `forecast` hive entry of
a continuous forecast is one entry per `(forecast, horizon)` with payload `{horizon_bars,
up_probability_ppm, quantiles_ticks, price_ref_ticks}` and `visible_from_ms = t_h + interval_ms` in the
instrument's own sequence: the first bar strictly after the bar at which the realisation became public,
so no agent reads another agent's statement on a horizon that is still open, and the settle phase of
`t_h` (where `forecast_resolved` is written) precedes any observation that could read it. There is no
`resolution` entry for a continuous instrument; the realised price is the tape, which every agent sees
through the ordinary `MarketView`. `Hive.write_forecast` gains keyword-only `horizon_bars: int = 0`,
`quantiles_ticks: tuple[int, ...] | None = None`, `price_ref_ticks: int = 0` and `resolves_at_ms` (the
`t_h` the engine computed) with `resolved_at_ms` ignored when `horizon_bars > 0`; `HiveView.forecasts`'s
scope "settled markets only" reads "resolved horizons only" on a continuous instrument.

**Calibration ledgers per kind and horizon** (12.2 and 10.3 as generalised, ruling R161). The memory's
calibration table and `pmx.metrics.calibration.calibration_table` bin `up_probability_ppm` into the ten
deciles of `CALIBRATION_BINS` with `n_yes` counting `realised_sign > 0` (a tie counts half: the ledger
stores `n_yes_x2`, twice the count, so that a tie adds `1` and an up adds `2`, and `yes_rate_ppm =
round_half_up(PPM_ONE * n_yes_x2, 2 * n)`); the ledger key is `(kind, f"h{h}", bin)`, carried in the
existing `CalibrationBinView` with `category = kind`, `horizon_bucket = f"h{h}"` (a string matching
`RE_HORIZON_BUCKET`; `HORIZON_BUCKETS` stays the four binary buckets, because horizons are per-run config
and it is a module constant, ruling R188) and `n_yes_x2` as a defaulted field beside `n_yes` (`n_yes =
n_yes_x2 // 2`; every ratio a consumer computes reads `n_yes_x2` over `2 * n`, one spelling in
`pmx.metrics.calibration`, ruling R194: a consumer computing `n_yes / n` on a continuous slice would
otherwise be off by two or lose the tie). A binary ledger is unchanged. `ece_ppm` and
`sharpness_ppm` are computed per `(kind, horizon)` slice and reported per slice; nothing is pooled across
kinds.

**Who owns what.** E3 (`pmx.scoring`, `pmx.metrics.calibration`) owns `directional_brier_micro`,
`pinball_micro`, the two skills, the per-instrument aggregation and the per-kind ledgers, and asserts the
random-walk identity and the tie rule (`default_horizons_bars` is `pmx.types`', D1's, because `RunConfig`
resolves it before hashing, ruling R188); E5 (`pmx.engine.runner`,
`pmx.metrics.projection`) owns the reference and realisation lookups, the `forecast_resolved` and
`instrument_closed` events, the carried horizon statements, the hive writes and the rows that carry
`kind` and `horizon_bars`; A1 owns the `random_walk` family and the five finance families of 17.7; E1
**fills** `MarketView.kind`, `tick_size_micro`, `point_value_micro`, `session_calendar_id`,
`hours_to_next_bar` (the gap to the instrument's next bar, public from the calendar), `underlying_id`,
`twins` and `cash_events`, which are D1's defaulted fields of 8.3 (ruling R188), so A1 reads them from one
declared shape.

### 17.6 Claims, leaderboards and folds per kind and provider

**Every claim, every leaderboard row and every opportunity card carries the asset class** (rulings R162
and R163). Section 12.6's bar is applied **per `(kind, provider)`**, nothing is pooled across kinds any
more than across providers, and:

- the claim id becomes `c-<dataset_hash[:8]>-<kind>-<provider>-h<horizon_bars>-<genome_hash[:16]>`
  (17.8), with `horizon_bars = 0` for a binary and the claim's declared horizon for a continuous kind
  (`pmx claim --kind <kind> --provider <provider> [--horizon-bars <h>]`, default the one-day horizon of
  `default_horizons_bars`); `sealed_test_opened` and `claims/access.jsonl` gain `kind` and
  `horizon_bars`; `open_sealed_test` gains keyword-only `kind: str = "binary"` and returns the sealed
  ids of that kind and provider only; the refusal rule of 12.8 keys on `(dataset_hash, kind, provider,
  horizon_bars, genome_hash)`;
- for a continuous kind the **unit** of the claim is an `(instrument, ISO week)` cell, not an instrument:
  the per-unit skill is `RANDOM_WALK_BRIER_MICRO` minus the mean directional Brier of the agent's
  resolved forecasts at the claim's horizon in that cell, the per-unit PnL is the realised PnL of the
  fills, fees and cash events booked in that week, `block_key` is the week (`f"w{iso_year}-{iso_week:02d}"`
  of the cell, or the `cluster_id` when the instrument has one, ruling R118), and `n_markets >=
  CLAIM_MIN_MARKETS` counts cells (`n_units` in the claim, `n_markets` kept as the field name);
- part 1 pairs against the random walk per unit (the baseline's per-unit skill is `0`, so the paired
  bootstrap of 12.4 is the plain one); part 2 is unchanged in form; part 3's `K` counts candidates
  scored against `(dataset_hash, kind)`; part 4's permutation shuffles **realised directions across
  instruments within a week** (PRD v4 section 3, ruling R190): for each permutation, the per-forecast
  `realised_sign` values of the forecasts made at the same bar `t` for the same horizon `h` are permuted
  across the instruments of that ISO week that carry a forecast at `(t, h)`, the forecasts held fixed,
  unmatched forecasts left in place, and the per-cell directional skill recomputed
  (`permutation_null(..., realised_signs=, bar_keys=)`, 12.4); `price_realised_ticks` is not shuffled,
  because instruments are quoted in different units and a permuted pinball loss is meaningless, so part 4
  tests direction and `pinball_skill` carries no permutation part;
- the honest expectation is recorded in the claim's `note`: on a continuous kind most agents will not
  clear the bar, and `no_demonstrated_edge` is the expected verdict, reported as such (PRD v4 section 3,
  AC-25: a claim is produced per asset class for the champion whatever its sign).

The **leaderboard** (12.10) row key becomes `(agent_id, kind, provider, horizon_bars, fold, category |
"all", hardness_tag | "all")`; `LeaderboardRow` gains `kind: str`, `horizon_bars: int` (`0` on a binary
row), `vendor: str`, `n_units: int`, `n_quantile_forecasts: int` and `pinball_skill: Interval` (`n: 0`
on a binary row); on a continuous row `brier_tw_micro` is the mean directional Brier at the row's horizon,
`skill` the directional skill interval, `log_micronats` is `0`, `ece_ppm` is the `(kind, horizon)`
ledger's, and the pinned baseline row is `random_walk` (`skill.point == 0` by construction) where a
binary slice pins `market_follower`. `PerMarket` gains `kind`, `horizon_bars`, `unit_key` (the market id
on a binary, `f"{market_id}/{iso_week_key(cell_ms)}"` on a continuous cell, one spelling in `pmx.metrics.stats`, ruling R219), `dir_brier_micro`,
`pinball_micro`, `baseline_pinball_micro`, `n_resolved` and `n_cash_events`; `MarketResult` gains
`kind`, `vendor` and `last_price_ticks`, and its `outcome` is `-1` and `life_mean_price_bp` is the mean
close in ticks on a continuous instrument; `AgentResult` gains `pinball_skill: Interval`,
`exposure_by_kind: tuple[tuple[str, int], ...]` (mean absolute marked notional per kind in cents, sorted
by kind) and `n_cash_events`; `Descriptors` is unchanged, and `category_coverage_ppm` counts kinds as
categories on a continuous row. Every `GET /runs/{run_id}/leaderboard` and `/claims` answer of 12.12
gains `?kind=&horizon_bars=` filters and the new columns, with no other route change.

**Folds** (7.7, 12.7) are unchanged in form and generalised in key: a continuous instrument belongs to
**every** fold whose span it has bars in, because it does not resolve; `make_folds` places a continuous
instrument's **bars** by `t_ms` against the fold spans of 7.7 (the count-quantile cuts of amendment C1c,
ruling R247, which replaced this paragraph's month edges; the thirteen edges stay for the rolling folds), a
run on fold `f` carries an instrument if it has at least one bar inside the fold's span and clips the run's
`t0_ms`/`t1_ms` to that span, and the forced flat of 17.3 closes it at the fold's edge. A binary belongs to
one fold by `resolved_at_ms` and its cluster group, as 7.7 says. The sealed fold of a continuous kind is
therefore the sealed **span** `[validation_end_ms, freeze_ms - MS_PER_DAY)`, and `open_sealed_test`
returns the instrument ids that have a bar in it; the manifest's `split` block gains
`n_instruments_train`, `n_instruments_validation` and `n_instruments_sealed` (17.9).

**Cross-domain detectors** (R2f, wave 8) emit `OpportunityEvent`s exactly as 16.4 declares, with two
generalisations recorded here so that `opportunity.v1.json` is widened once, by C2: `detector_id` gains
`cross_domain`, `currency` accepts any quote currency of 17.1, `tradable_for_money` is `false` when any
leg is `mana` **or** any leg's vendor is `yahoo` (an unofficial tape is not a bankable edge), and every
event carries `kinds: list[str]` and `providers: list[str]` beside `market_ids`.

### 17.7 The wave 3b module map, the new families and the two new architecture rules

Section 13 carries one owner per new file (ruling R166):

| File | Owner | What it is |
|---|---|---|
| `src/pmx/schemas/instrument.v1.json`, `cash_event.v1.json`, `session_calendar.v1.json`, `forecast.v1.json` | C1b | this amendment's four schemas (17.1, 17.3, 17.2, 17.5) |
| `src/pmx/data/importers/binance.py`, `kraken.py`, `coinbase.py`, `bybit.py` | F1 | klines, trades and funding history into `spot_crypto` and `perp` instruments with the venue's scales and `twins`; `import_binance(*, client, window_start_ms, window_end_ms, freeze_ms, symbols, interval_min=60, limit=None) -> tuple[ContinuousInstrument, ...]` and the same keyword-only shape for the other three (7.12's rule, ruling R93's arguments) |
| `src/pmx/data/importers/yahoo.py`, `frankfurter.py`, `ecb.py` | F2 | Yahoo chart v8 (equities, ETFs, continuous futures, FX) with the `yahoo` vendor label, throttle and cache, splits and dividends from the chart `events` into `CashEvent`s, roll detection into `roll` events with `roll_source = "vendor"`; Frankfurter and ECB daily reference rates as `fx` instruments on the daily grid (the official anchor) |
| `src/pmx/data/news/edgar.py`, `fred.py`, `release_calendar.py`, `cboe.py` | F3 | SEC submissions into `NewsItem(source="edgar", kind="filing")` with the acceptance time as `published_at_ms`; ALFRED vintages into `NewsItem(source="fred", kind="release")` visible from the vintage date; the static FOMC, CPI and payrolls calendar (`src/pmx/data/calendars/releases.v1.json`, also F3's); VIX history as a daily `NewsItem(source="cboe", kind="release")`. `news.v1.json` gains the three sources and the two kinds (C1b widens the schema, see 17.9) |
| `src/pmx/lexicons/fin_<topic>.v1.json` | F3 | the finance lexicons for `newsbayes` (`fin_rates`, `fin_earnings`, `fin_crypto`, `fin_macro`), indexed by `newsbayes.lexicon_id` values `12..15` (`LEXICON_COUNT` stays `12` for the categories; `FINANCE_LEXICONS` is a second tuple) |
| `src/pmx/data/sessions.py` | D1 (ruling R174; applied by gate G2, because E1's `Calendar`, E2's `Execution` and the loader call it in wave 2 and architecture rule 11 forbids them a copy) | `in_session`, `next_bar_ms`, `load_calendar`, the synthesised `continuous` calendar and the generator the static calendars are built with; `SessionCalendar` itself is a `pmx.types` dataclass |
| `src/pmx/data/calendars/*.json` | F4 | the static calendars (`fx_weekly`, `xnys`, `xnas`, `arcx`, `cme_globex`) generated for the window through `pmx.data.sessions` and copied into the dataset by the builder; `continuous` is never a file (ruling R185) |
| `src/pmx/data/universe_finance.py` | F4 | the universe of PRD v4 2.2 chosen at the window start from a dated list (`universe_finance.v1.json` beside it, F4's), reproducible from that input |
| `src/pmx/lexicons/kalshi_series_subjects.v1.json`, `kalshi_series_categories.v1.json` | D2 | the sealed Kalshi series-to-subjects and series-prefix-to-category maps of rulings R169 and R170 |
| `src/pmx/agents/families/carry.py`, `basis.py`, `pairs.py`, `vol_regime.py`, `calendar.py`, `random_walk.py` | A1 | the five finance families and the baseline, below |
| `src/pmx/analysis/cross_domain.py` | R2f | binary versus underlying, funding and basis, cross-venue crypto, macro releases with ALFRED clocks, post-filing drift |
| `tests/test_import_crypto.py`, `tests/fixtures/f1/` | F1 | |
| `tests/test_import_yahoo_fx.py`, `tests/fixtures/f2/` | F2 | |
| `tests/test_finance_news.py`, `tests/fixtures/f3/` | F3 | |
| `tests/test_sessions_universe.py` | F4 | |
| `tests/e2e/test_e2e_1b_multi_asset.py`, `tests/e2e/test_e2e_2b_cross_domain.py` | gate G3b, gate G8 | the two end-to-end tests of PRD v4 section 7 |

**The new families** (10.5 as extended; A1 owns them, wave 3, and every reading rule of 10.5 holds):

| Family | Role | Genes `name: lo..hi (step) [default]` | Rule |
|---|---|---|---|
| `random_walk` | belief, baseline | none (`evolvable: False`) | `up_probability_ppm = 500_000` and every quantile `= price_ref_ticks` on every continuous instrument and horizon; `ppm_from_bp(last_price_bp)` on a binary; trades nothing. Zero skill by construction (17.5) |
| `carry` | belief | `lookback_events: 1..30 (1) [8]`, `lean_permille: 0..2000 (50) [500]`, `min_rate_ppm: 0..5000 (50) [100]` | on a `perp`, the mean `rate_ppm` of the last `lookback_events` applied `funding` events in `MarketView.cash_events` (visible once their application bar has completed, 17.3, ruling R183) leans `up_probability_ppm` against the payer: `500_000 - sign(mean_rate) * min(abs(mean_rate), 5_000) * lean_permille // 10` when `abs(mean_rate) >= min_rate_ppm`, else the random walk; on `fx` with a carry schedule the same on the schedule's rate |
| `basis` | belief | `basis_window_bars: 2..168 (2) [24]`, `threshold_bp: 0..500 (10) [50]`, `lean_permille: 0..2000 (50) [500]` | on a `perp` whose `underlying_id` is in the run, `basis_bp = bp_ratio(perp_last - spot_last, spot_last)`; leans the perp down and the spot up by `ppm_from_bp(basis_bp) * lean_permille // 1_000` when `abs(basis_bp)` exceeds `threshold_bp` over the window's mean, else the random walk |
| `pairs` | belief | `spread_window_bars: 5..168 (5) [48]`, `entry_z_milli: 500..4000 (100) [2000]`, `lean_permille: 0..2000 (50) [500]` | on two `twins` (17.1) both in the run, the integer z-score (milli) of the log-free ratio `bp_ratio(a_last - b_last, b_last)` against its window mean and `isqrt` deviation; leans the rich leg down and the cheap one up when `abs(z) >= entry_z_milli`, else the random walk |
| `vol_regime` | overlay | `vol_window_bars: 5..168 (5) [24]`, `gate_permille: 0..1000 (50) [700]` | scales the inner family's lean toward the random walk by `gate_permille` when the realised volatility (integer standard deviation of bar-to-bar `bp_ratio` returns over the window) is in the top decile of the instrument's own history to date, or when the `cboe` VIX item visible at `now_ms` exceeds the agent's memory of its median; a gate, never a signal |
| `calendar` | overlay | `session_open_bars: 0..4 (1) [1]`, `release_window_bars: 0..8 (1) [2]`, `mode: 0..1 (1) [0]` | `mode 0` flattens the inner family's lean to the random walk in the first `session_open_bars` of a session and within `release_window_bars` of a `release_calendar` item; `mode 1` doubles it there; reads only the sealed calendar and the release items visible at `now_ms` |

`trend`, `revert`, `breakout` and `volume` run unchanged on a continuous instrument with `last` read in
ticks and `move` converted through `bp_ratio(move_ticks, last_ticks)` in place of `ppm_from_bp(move)`
(A1 records the one-line generalisation per family); `timedecay` is binary-only and states the random
walk elsewhere; `newsbayes` takes a finance lexicon id; `kelly` sizes `target_position` in milli-units
through `mark_value_cents`; `calibrator` and `stacker` read the generalised records. The default roster
of 10.5 is unchanged; `random_walk` joins every population as a fixed member beside
`top_k_extremized_mean`, for the reason `market_follower` does.

**Two rules join the nine of `tests/test_architecture.py`** (ruling R172), both green on the tree of
2026-09-08 where none of the files exists:

10. **The data layer never imports the engine.** Nothing under `src/pmx/data/` imports `pmx.engine`,
    `pmx.agents`, `pmx.metrics` or `pmx.optimizer`. An importer, a calendar or the builder that reached
    into execution would make the seal depend on the engine version.
11. **Session membership is decided in one place.** `in_session` is bound only in
    `src/pmx/data/sessions.py` (D1's file since ruling R174, so it exists at gate G2); `pmx.engine.calendar`,
    `pmx.engine.execution` and the loader call it and never redefine it, so
    "a bar outside its calendar does not exist" has one implementation and one test.

### 17.8 v4 identifier formats

The continuation of the tables of sections 2 and 16.7. Every regex is a constant beside its owning
module (ruling R121); the id patterns of `journal.v2.json` and `actions.v2.json` are widened here, those
of `market.v2.json` and `dataset.v1.json` are contract issues (17.9).

| Entity | Format | Regex | Assigned by |
|---|---|---|---|
| Instrument (every kind) | `<provider>-<slug>` | `^(kalshi\|manifold\|polymarket\|metaculus\|demo\|binance\|kraken\|coinbase\|bybit\|xnys\|xnas\|arcx\|xcme\|xnym\|xcec\|xcbt\|otcfx)-[A-Za-z0-9._-]{1,96}$` | the importer; `slug` is the venue's symbol, dots and dashes kept (`binance-BTCUSDT`, `binance-BTCUSDT.PERP`, `xnas-AAPL`, `xcme-ES`, `otcfx-EURUSD`) |
| Provider | one of seventeen | `^(kalshi\|manifold\|polymarket\|metaculus\|demo\|binance\|kraken\|coinbase\|bybit\|xnys\|xnas\|arcx\|xcme\|xnym\|xcec\|xcbt\|otcfx)$` | this contract; the equity and futures venues are ISO 10383 MIC codes in lower case, `otcfx` is the over-the-counter FX book |
| Vendor | one of twelve | `^(kalshi\|manifold\|polymarket\|metaculus\|demo\|binance\|kraken\|coinbase\|bybit\|yahoo\|frankfurter\|ecb)$` | the importer; a binary's vendor is its provider |
| Kind | one of six | `^(binary\|spot_crypto\|perp\|fx\|equity\|future)$` | this contract, `INSTRUMENT_KINDS` |
| Session calendar | lowercase slug | `^[a-z][a-z0-9_]{0,31}$` | F4 for a file; `continuous` is reserved, synthesised by the loader and never a file (ruling R185), and is the calendar of every binary and every crypto instrument |
| Cash event | `ce-<sha256(canonical_json([market_id, kind, t_ms, detail]))[:16]>` | `^ce-[0-9a-f]{16}$` | the importer (data events) or `pmx.engine.execution` (engine events), both through `pmx.types.cash_event_id` |
| Cash event kind | one of seven | `^(funding\|dividend\|split\|roll\|borrow_fee\|carry\|forced_flat)$` | this contract, `CASH_EVENT_KINDS` (`carry` is ruling R177's) |
| Fee model | one of four | `^(pq_permille\|notional_bp\|per_contract\|zero)$` | this contract, `FEE_MODELS` |
| Claim | `c-<dataset_hash[:8]>-<kind>-<provider>-h<horizon_bars>-<genome_hash[:16]>` | `^c-[0-9a-f]{8}-(binary\|spot_crypto\|perp\|fx\|equity\|future)-(<provider>)-h[0-9]{1,5}-[0-9a-f]{16}$` | `pmx claim`; one per `(dataset_hash, kind, provider, horizon_bars, genome_hash)`. The v2 form `c-<hash8>-<provider>-<genome16>` is still accepted by `journal.v2.json` so a journal written before this amendment validates, and is never written again |
| Live forecast | `lf-<yyyymmdd>-<agent_id>-<market_id>` | the regex of section 2 with the widened provider group | L1 |
| News item | `<source_code>-<yyyymmdd>-<idx:04d>` | `^(wce\|wasof\|wb\|gd\|mfc\|edg\|fred\|cboe)-[0-9]{8}-[0-9]{4}$` | F3; `edg` SEC EDGAR, `fred` ALFRED vintage, `cboe` VIX |
| Horizon bucket | a binary bucket or `h<bars>` | `RE_HORIZON_BUCKET = ^(30d\|7d\|2d\|0d\|h[0-9]{1,5})$` | `pmx.types` (ruling R188); `HORIZON_BUCKETS` stays the four binary strings |

### 17.9 What amendment C1b does not own

C1b owns `docs/CONTRACTS_V2.md` (this section, 15.9, and every in-place amendment recorded there), the
four new schemas, `journal.v2.json` and `actions.v2.json` (widened here), `tests/test_contract_schemas.py`,
`tests/test_architecture.py` and the fixtures under `tests/fixtures/contract/`. **A section of this
document is never a contract issue** (ruling R136), so every normative passage this amendment changes is
amended in place: sections 1, 3, 5.2 to 5.4, 7.2, 7.4, 7.6 to 7.9, 8.1, 8.2, 8.4 to 8.9, 9.2, 9.3, 9.5,
10.3, 10.4, 12.1 to 12.4, 12.6 to 12.8, 12.10, 12.11, 13, 13.1, 14, 16.1 and 16.2. What is left is code or a schema in a
file another package owns, listed with the gate that applies it (ruling R171):

| Issue | File and owner | Applied by |
|---|---|---|
| R144, R145, R147, R148: `INSTRUMENT_KINDS`, `CONTINUOUS_KINDS`, `MICRO`, `MILLI`, `NOTIONAL_DENOMINATOR`, `BINARY_TICK_SIZE_MICRO`, `BINARY_POINT_VALUE_MICRO`, the five caps, `notional_micro`, `cash_out_cents`, `cash_in_cents`, `mark_value_cents`, `price_micro`, `Instrument` (with `bar_at` and `bars_before` on the base, R173), `ContinuousInstrument` (`bars: tuple[Bar, ...]`, `trades: tuple[Trade, ...]`, R173), `SessionCalendar`, `CashEvent`, `CASH_EVENT_KINDS` (seven, R177), `DATA_CASH_EVENT_KINDS`, `cash_event_id`, `split_position_milli`, `HorizonForecast`, `QUANTILE_LEVELS_PPM`, `RANDOM_WALK_UP_PPM`, `RANDOM_WALK_BRIER_MICRO`, `default_horizons_bars` (R188), `Market.instrument`, `MarketMeta.kind` and the continuous `MarketMeta` values of 7.2 through `meta_of` (R186), `Dataset.calendar`, `Dataset.sealed_market` (R182), `RunConfig.horizons_bars` and `RunConfig.kinds`, `BuildConfig.kinds` and `BuildConfig.min_traded_bars`, `Actions.horizon_forecasts`, the eight defaulted `MarketView` fields of 8.3 with `CashEventView` and `CASH_EVENTS_VIEW_MAX` (R181, R183, R188), `CalibrationBinView.n_yes_x2` (R194), the signed `PortfolioView.cash_cents` and `equity_cents` (R179, R180), `MarketQuality.tape_kind`, the `RejectReason` values `bad_horizon`, `bad_quantiles`, `RE_HORIZON_BUCKET` (R188), `INT63_MAX`, `TRADE_SIDES` gaining `buy` and `sell` (R173), `VENDORS`, and the widened `PROVIDERS`, `CURRENCIES` (17.1's quote currencies), `NEWS_SOURCES`, `NEWS_KINDS`, `NEWS_KIND_BY_SOURCE`, `NEWS_CODE_BY_SOURCE`, `RE_NEWS_ID`, `RE_LIVE_FORECAST_ID`, `RE_MARKET_ID`, `RE_PROVIDER`, `RE_CLAIM_ID` (without the last group `BuildConfig.__post_init__` refuses every F1 and F3 build as `InvalidConfigError`, R188), `DECISION_LATENCY_BARS` (16.2, R107; added by ruling R201) | `src/pmx/types.py` (D1) | gate G2, **applied** (ruling R201) |
| R165: the widened `id`, `provider` and `currency` patterns (`quality.tape_kind` and `wiki_subject_provenance` of rulings R167 and R169 are in the schema already, landed by the data package) | `src/pmx/schemas/market.v2.json` (C0's, edited by the data package now working in it) | gate G2, **applied** (ruling R201) |
| R149, R168, R170: the walk gains `instruments/` and `calendars/`; the manifest gains `kinds`, `instruments {per_kind, per_provider, per_vendor, n_cash_events {per_kind}, n_calendars}`, `schedules {fee: [ids], borrow: [ids], carry: [ids]}`, `split.n_instruments_train`, `n_instruments_validation`, `n_instruments_sealed`; `files.path` accepts `instruments/` and `calendars/`; `providers` and `news.sources[].source` widen (`counts.precap_per_provider_month`, `n_bars_only` and `n_category_fallback` of rulings R168 and R170 are in the schema already) | `src/pmx/schemas/dataset.v1.json` (C0's, same package) | gate G2, **applied** (ruling R201) |
| R149, R173, R182, R185: `seal_dataset`, `verify_dataset` and `load_dataset` walk `instruments/` and `calendars/`, validate `instrument.v1.json` and `session_calendar.v1.json`, refuse a bar of a `ContinuousInstrument` outside its calendar and never check a binary against one, map the file's `_ticks` fields onto `Bar` and `Trade`, clip a continuous instrument at `validation_end_ms` behind `Dataset.market` and expose the whole record through `Dataset.sealed_market`, synthesise the `continuous` calendar and refuse a `calendars/continuous.json`; `SCHEMA_FILES` gains the four names and `pmx/__init__.py` the four `*_SCHEMA` constants of 13.2 | `src/pmx/data/loader.py`, `src/pmx/data/schema.py` (D1), `src/pmx/__init__.py` (C0) | gate G2, **applied** (rulings R201 and R223) |
| R174: `pmx.data.sessions` (`in_session`, `next_bar_ms`, `load_calendar`, the synthesised `continuous` calendar, the exchange-calendar generator) moves from F4 to D1 so that it exists when E1, E2 and the loader need it; `docs/PLAN_V3_WAVES.md`'s F4 row still lists the file and is a contract issue for the gate (the contract wins for code, preamble); F4 keeps `data/calendars/*.json` and `universe_finance.py` | `src/pmx/data/sessions.py` (D1), `docs/PLAN_V3_WAVES.md` (the plan's author) | gate G2, **applied** (ruling R203) |
| R189: PRD v4 1.2's binary row (`tick_size_micro = 10_000`) and its rounding sentence contradict rulings R145 and R146 and the PRD's own invariant ("nothing written for prediction markets changes value", which `100` keeps and `10_000` breaks by a factor of one hundred); the PRD's 1.2 binary row reads `tick_size_micro = 100`, its rounding sentence reads "one rounding, at the end, against the agent for a cash movement; round half up for a score or a quantile", and its revision history gains a 1.1 entry citing R145, R146 and R189. The PRD defers the formulas to this amendment, so the point is this document's to decide and the preamble's PRD-wins rule is not engaged; the correction is recorded here rather than made because the PRD is not a file this amendment owns | `docs/PRD_V4_MULTI_ASSET.md` (the PRD's author) | gate G2, **applied** (ruling R201: the PRD's 1.2 binary row reads `100`, its rounding sentence reads R146's, and its revision history carries 1.1) |
| R165: `news.v1.json` gains sources `edgar`, `fred`, `cboe` and kinds `filing`, `release`, and the three news id codes | `src/pmx/schemas/news.v1.json` (C0's) | gate G3b |
| R129 and R164: `pmx.journal` gains `CashEventApplied`, `InstrumentClosed` and `ForecastResolved` (registered in `EVENT_TYPES` and `EVENT_CLASSES`), `OrderPlaced`, `Filled` and `FeeCharged` gain `"settle"` in `PHASES`, and the existing classes gain the optional `market_listed` and `forecast_recorded` fields; `journal.v2.json` admits the three events to `oneOf`, widens the three phase enums and promotes the new fields with `decided_at_ms` to `required` in the same commit that rebuilds the backtest fixture | `pmx.journal` (D7); the `oneOf`, the phase enums, the `required` lists and the fixture (C1b) | gate G2, **applied** (ruling R202) |
| R152, R173: `event_fill`, `slippage_ticks`, `clamp_price`, `envelope_bounds(bar, *, kind)`, the `market_view` keyword of `finalise_fill` and `truncate_for_cash` in `pmx.engine.liquidity`; `historical` reads the half-spread floor of 17.4; `applies_at` and the `calendars` argument in `pmx.engine.execution` (R174, R175) | `src/pmx/engine/liquidity.py`, `src/pmx/engine/execution.py` (E2) | wave 2, **applied** (rulings R204, R213 and R214) |
| R160: `Hive.write_forecast`'s four keyword-only arguments | `src/pmx/agents/hive.py` (A3) | gate G3 |
| R162, R190: `open_sealed_test(..., kind="binary")`, the claim id, the `(instrument, week)` units and the within-week permutation of `realised_sign` (`permutation_null(..., realised_signs=None, bar_keys=None)`); `claims.py` is the one caller of `Dataset.sealed_market` (R182) | `src/pmx/optimizer/folds.py` (O1), `claims.py` (O4), `pmx.metrics.stats` (E4) | gate G2 (E4, **applied**, ruling R219), gate G4 (O1, O4) |
| R166: `opportunity.v1.json` gains `cross_domain`, `kinds`, `providers` and the currency widening | `src/pmx/schemas/opportunity.v1.json` (C1's) | amendment C2 |
| R166: `.gitignore` and `pyproject.toml` package-data gain `data/calendars/*.json` and `lexicons/*.json` (already) | `.gitignore` (C0), `pyproject.toml` (U4) | gate G3b |

---

## 18. Discovery (amendment C1c): sensors, the hypothesis layer, minute grids, workflow genomes, cohorts

`docs/PRD_V5_DISCOVERY.md` makes two things the optimizer searches over that the build so far wrote by
hand: **which information an agent consumes** (the sensor gene) and **which rules it trades on** (the
hypothesis layer), with minute grids so that sub-hour statements are testable and workflow genomes so
that the whole decision graph is one heritable object. This section is the amendment the agents wave
(`docs/PLAN_V3_WAVES.md` lots 5b and 6: S1, S2, F5, DS1, DS2, A1..A6, FM1, O1..O4) is built against,
and it lands **after** gate G2 and before that wave for the reason sections 16 and 17 did: fourteen
packages written blind of each other must fit, and the engine wave showed what a vague sentence costs
(five packages, 30 cross-package disagreements, 69 contract issues). Everything below binds exactly as
sections 1 to 17 do. Where it changes earlier text, the earlier text has already been amended in place
and the change is a ruling in 15.10; the two reviews of 2026-09-08 and 2026-09-09 (decisions D-R1 to
D-R14 and D-S1 to D-S14) are landed the same way, each in the section the review names, and 18.5 holds
the one object both reviews and PRD v5 share, the **cohort**.

Three sentences carry the design. **What is not sensed is not seen**: an observation is assembled by the
filters of 5.4 exactly as before and then narrowed by subtraction to the agent's sensor set, so a sensor
set can only ever remove a field, never add one, and the as-of law needs no second proof. **Knowledge is a
record, never a sentence**: a rule is data in a closed vocabulary with an author, a birth instant, a
pre-registered family, a test record and a live record, and only a rule that replicated out of time on
data its promotion never read becomes visible to anyone. **Nothing already built is invalidated**: the
default sensor set is every sensor and is byte-identical to the builder that predates the hook, the linear
family composition of 10.1 is the degenerate workflow, and a dataset built before this amendment loads,
seals and replays as it did.

### 18.1 The sensor catalogue, the sensor gene and the sensor budget

**The catalogue is closed** and lives in `pmx.sensors.catalogue` (S1) as `SENSORS: Mapping[str,
SensorSpec]`, keys sorted, with `SENSOR_NAMES = tuple(sorted(SENSORS))` and `CATALOGUE_HASH =
sha256(canonical_json([spec.to_dict() for spec in SENSORS.values()]))`, so a run records which catalogue it
read. The declaration document is `src/pmx/schemas/sensor.v1.json` (C1c) and the normative table is the
fixture `tests/fixtures/contract/sensor.catalogue.json`, which S1 implements exactly:

```python
@dataclass(frozen=True, slots=True)
class SensorSpec:
    name: str                      # section 18.7's sensor regex; one of the fifteen below
    version: str                   # "<name>.v1": bumps when the block's features or the lag change
    cost_units: int                # sensor units per bar (PRD v5 1.1's column), 0..SENSOR_COST_MAX = 10
    granularity_ms: int            # DERIVED (ruling R287): max(SOURCE_GRANULARITY_MS[s] for s in sources), 0
                                   # for a sensor with no source; the COARSEST stamp any of its sources carries
    lag_ms: int                    # DERIVED (ruling R287): max(SAFETY_LAG_MS_BY_SOURCE[s] for s in sources), 0
                                   # for a sensor with no source; the LONGEST lag the builder applies to one of them
    sources: tuple[str, ...]       # the NEWS_SOURCES it reads, () for a tape or engine sensor
    market_fields: tuple[str, ...] # the MarketView fields it gates (8.3), sorted
    observation_fields: tuple[str, ...]   # the Observation fields it gates, sorted
    per_market: bool               # True: one block per open market; False: one block per observation (hive_reputation)
    features: tuple[SensorFeatureSpec, ...]   # the SensorBlock layout below, in block order
    def to_dict(self) -> dict[str, object]: ...
```

| Sensor | Gates (`MarketView` unless stated) | Source and granularity | `lag_ms` | `cost_units` |
|---|---|---|---|---|
| `tape` | `bars` (the price fields of every `Bar`: `open_bp`, `high_bp`, `low_bp`, `close_bp`, `vwap_bp`, `t_ms`), `first_price_bp`, `last_price_bp` | the instrument's own bars, grid | 0 | 0 (**always on**, below) |
| `microstructure` | `best_bid_bp`, `best_ask_bp`, `trades`; inside every `Bar`: `yes_bid_bp`, `yes_ask_bp`; the research kind `history` | prints and quotes, grid | 0 | 1 |
| `volume_profile` | `volume_milli_7d`, `volume_milli_to_date`, `n_trades_to_date`, `cash_events` (ruling R233); inside every `Bar`: `volume_milli`, `n_trades`, `open_interest` | bars and applied cash events, grid | 0 | 1 |
| `cross_asset` | `underlying_id`, `twins` | the run's other instruments, grid | 0 | 1 |
| `calendar` | `close_at_ms`, `session_calendar_id`, `hours_to_next_bar` | the venue's published schedule, grid | 0 | 0 |
| `wiki_daily` | `news` items of sources `wikipedia_current_events` and `wayback`, in `MarketView.news` and `Observation.news`; the research kind `news` | Wikipedia Current events, per-bullet revision time (D-R3, 5.5), floor `SAFETY_LAG_MS_DEFAULT` | 21_600_000 | 1 |
| `comments` | `news` items of source `manifold_comment` | Manifold comments, `createdTime`, millisecond | 60_000 | 1 |
| `hn` | `news` items of source `hn` | Hacker News through Algolia `search_by_date`, `created_at_i`, second | 300_000 | 2 |
| `gdelt_recent` | `news` items of source `gdelt` | GDELT DOC 2.0 `seendate`, 15 minutes | 900_000 | 2 |
| `filings` | `news` items of source `edgar` | SEC EDGAR acceptance time, second | 60_000 | 2 |
| `macro_releases` | `news` items of sources `fred` and `cboe` and the release calendar of 17.7 | ALFRED vintages and release times; `cboe` is day-stamped, so the derived pair is a day and six hours | 21_600_000 | 1 |
| `wiki_asof` | the research kind `wiki_asof` (a granted request's `ResearchGrant` payload) | point-in-time revisions, day | 21_600_000 | 3 |
| `hive_insights` | `Observation.hive`: `HiveView.insights`, `lessons`, `resolutions`, `forecasts`, `prev_bar_forecasts` | the hive, bar | 0 | 1 |
| `hive_reputation` | `Observation.hive`: `HiveView.reputations` | the hive, bar | 0 | 1 |
| `memory` | `Observation.memory` | the agent's own memory, bar | 0 | 0 |

The costs are PRD v5 1.1's column verbatim; the lags are **defaults the first minute build reports
against**, not laws (no measurement of a source's publication delay exists yet). **`granularity_ms` and
`lag_ms` are derived, never hand-written** (ruling R287): they are the maxima of `SOURCE_GRANULARITY_MS`
and of `SAFETY_LAG_MS_BY_SOURCE` (18.3) over the sensor's `sources`, and `0` for a sensor with none, so
the column a reader consults when asking whether a sensor can leak names that sensor's **worst** source
and never its best. The builder still stamps each item with its own source's lag through 5.5's
per-source table, so nothing is slowed down by the derivation and a sensor cannot see an item before the
dataset says it was visible; S1 asserts the two identities against `pmx.types` and the fixture carries
the derived values. `macro_releases` therefore reads a day and six hours, not a second and nothing,
because `cboe` is day-stamped.
`SENSOR_BUDGET_UNITS_DEFAULT = sum(cost_units) + RULE_PROPOSAL_COST_UNITS = 18` (ruling R281): the full
diet costs `17` and the one unit above it is the headroom a full-diet genome needs to propose a rule at
all.

**The gene.** `Genome.sensors: tuple[str, ...]` (10.1, A1) is sorted, unique, drawn from `SENSOR_NAMES`,
**always contains `"tape"`**, and is always rendered by `to_dict()` (the explicit full tuple for the eight
v1 archetypes of 10.5, so a genome names its diet and `genome_hash` covers it). A genome that omits `tape`
is refused by `genome_from_dict` and by `make_agent` with `InvalidConfigError`: a view without a price is
not a view an agent can decide on (every family of 10.5 reads `last_price_bp`, the forecast record of 8.4
carries `500_000` for an agent that never saw the market, and the alternative, defining what a tape-less
view answers, would be a second observation shape for a diet nobody asked for). A genome that names a
sensor outside the catalogue is refused the same way (`resolve_sensor_set`, E1's hook, already does).
Every `FamilySpec` (10.1) carries `required_sensors: frozenset[str]`, the sensors its rule reads (`volume`
needs `volume_profile`, `newsbayes` needs at least one news sensor, `carry` needs `volume_profile`,
`calibrator` with the hive on needs `hive_insights`, `stacker` needs `hive_reputation`, `rule_follower`
needs `hive_insights`); `genome_from_dict`, `make_agent`, `mutate` and `structural_mutate` refuse or never
produce a genome whose `sensors` omit a required sensor of its family, its `inner` or a `member`.
Mutation adds or removes one sensor (`evolution.mutation`, probability `sensor_mutation_permille` of
`EvolutionConfig`, default `100`), never `tape` and never a required one; crossover is uniform per sensor
name between the two parents' sets.

**The hook, made normative** (8.3, ruling R230). `build_observation(..., sensors=genome.sensors)`: the
keyword is what E1 shipped, `None` means every sensor and is byte-identical to the builder without it, a
set is applied by **subtraction** over what the as-of filters produced, and a field the set did not buy is
**absent** from the view and from the payload, never zeroed and never `None`: reading it raises
`SensorAbsentError` (13.1, ruling R232), `hasattr` raises too, and `to_dict()` omits the key. Three
gates go one level below a top-level field and are the same subtraction applied to a nested payload (ruling
R233): the `Bar` fields of `volume_profile` and `microstructure` inside `MarketView.bars` (a bar rendered
without `volume_milli` is a `SensedBar` with the same absence semantics; `tape` keeps the six price and
time fields of every bar), the `HiveView` fields split between `hive_insights` and `hive_reputation`
(`Observation.hive` is present when either is bought and carries only the bought half), and `news` items
filtered by `SENSOR_BY_NEWS_SOURCE` (`pmx.sensors.catalogue`, the source-to-sensor map of the table above;
`Observation.news` and `MarketView.news` are present when at least one news sensor is bought and carry
the items of the bought sources only). A `ResearchRequest` whose kind's sensor is not in the diet
(`history` needs `microstructure`, `news` needs `wiki_daily`, `wiki_asof` needs `wiki_asof`) is
`action_rejected(bad_research)`; a granted request still costs `RESEARCH_UNIT_COST[kind]` research units:
the **research budget** of 8.1 pays for on-demand grants and stays a per-run stock, the **sensor budget**
below pays for standing subscriptions and is a per-bar cap, and the two are distinct on purpose (the hook's
report asked which one prices a grant: the research budget does, and the sensor gates whether the request
may be made at all).

**What a run records** (rulings R231 and R274). `Observation.sensors: tuple[str, ...]` is the resolved
set, sorted (the full `SENSOR_NAMES` when the genome bought everything, so a catalogue change is visible
on the face of every observation); `observation_built` gains `sensors: list[str]` and `run_started` gains
`sensor_catalogue_hash: str`; `RunConfig.sensor_catalogue_hash: str = ""` names the catalogue a run must
read (`""` meaning the shipped one; `run_backtest` raises `InvalidConfigError` when a non-empty value
differs from `CATALOGUE_HASH`, exactly as it checks `liquidity_params_hash`). The runner passes
`sensors=genome.sensors` (today it passes `None` to every agent, BUILD_STATE 8.7); a roster whose agents
all buy everything therefore journals the same bytes it does today except the two new fields.

**The `SensorBlock`** (S1). Every sensor is a pure function `sense(view: SensorInputs, *, now_ms: int,
spec: SensorSpec) -> SensorBlock` from the as-of dataset views of 8.3 to an integer block.
**`SensorInputs` is declared in 12.11** (ruling R278), field by field, beside the other structures three
packages code blind against: S1 writes fifteen `sense` bodies against it, E1 fills it in the observe
phase, and FM1's proxy matrix fills it per `(market, bar)` with no observation in sight, so it is not a
shape any of the three may invent.

```python
@dataclass(frozen=True, slots=True)
class SensorBlock:
    sensor: str; version: str          # SensorSpec.name and .version
    market_id: str | None              # None when spec.per_market is False (hive_reputation on the shipped
                                       # catalogue and no other sensor, ruling R286), the market's id otherwise
    values: tuple[int, ...]            # one per spec.features entry, in block order, each clamped to [lo, hi]
    def to_dict(self) -> dict[str, object]: ...
```

`spec.features` is a tuple of `SensorFeatureSpec` (`pmx.sensors.catalogue`, S1): 16.5's `FeatureSpec`
fields (`index`, the position inside the block; `name`, `unit`, `lo`, `hi`, `scale`, `description`, `source
= sensor name`, `asof_only = True`), **`sentinel: int`** (the value a missing input takes, ruling R285)
and **`features_v1_index: int | None`**, the entry's position in the
`features.v1` vector when the feature is one of its thirty-seven fields and `None` otherwise.
**`features.v1` is unchanged**: its thirty-seven fields keep 16.5's order, names and bounds, and every one of them but the
six of the `portfolio` block (indices 31 to 36, the agent's own book, gated by no sensor) belongs to
exactly one sensor block through `features_v1_index` (the `category` block's two fields sit under `tape`,
the always-on sensor, because a market's category and provider are metadata known before its first bar).
The features outside `features.v1` (every news sensor but `wiki_daily`, the hive and memory blocks, the
additions to the market blocks) are available to a rule and to the `features` step of 18.4 from the first
build; appending them to a torch policy's vector is a `features.v2` that belongs to R3a and amendment C2,
not to this one. **A `torch_policy` genome's diet covers its own vector** (ruling R299): the family's
`required_sensors` is every sensor carrying at least one `features_v1_index` (`tape`, `calendar`,
`microstructure`, `volume_profile`, `cross_asset`, `wiki_daily`), so `genome_from_dict` and `mutate`
refuse a torch genome whose diet would feed the thirty-seven-wide vector a mix of measured values and
sentinels. A learned policy scored on a distribution its training never saw is not a diet experiment,
it is a broken input, and the sensor gene has no way to tell the two apart from the outside.

A block's feature names are the closed vocabulary 18.2's predicates draw from
(`pmx.rules.vocabulary.FEATURE_NAMES`, S2, is exactly the union of `spec.features[*].name` over the
catalogue, seventy-five names on the shipped fixture, unique across sensors, asserted by S2's test). A
missing input (no quote, no item, no memory) takes **`spec.sentinel` and nothing else** (ruling R285),
never `None` and never a value a reader has to infer from prose: a block is fixed-width and every
sentinel is a field of the catalogue. The fixture fills all seventy-five by one rule, which S1 asserts:
a **signed** quantity's sentinel is `0` (an unknown gap, return or z score is no gap, and never the
floor of its range, which would read minus one hundred percent over the first ninety bars of every
market and be the strongest signal in the miner's search); a `minutes_since_*`, `bars_since_*`,
`bars_to_*` or `*_days_since_*` count's sentinel is its `hi` of `100000` (nothing has happened yet is
arbitrarily long ago); every other feature's sentinel is its `lo`, which is `0` on every feature of the
shipped catalogue. S1's test asserts `lo <= sentinel <= hi` for every feature and that no signed
feature's sentinel is its `lo`. The contents of the blocks outside `features.v1` are this amendment's
defaults, which the first build reports against; S1 may not add, remove or rename a feature without
bumping the sensor's `version` and therefore `CATALOGUE_HASH`, and the fixture's `catalogue_hash` is
`CATALOGUE_HASH` (S1's test asserts equality). Blocks are computed in the `observe` phase from the same
views the agent receives, are never journaled (they are a projection of the observation, 9.5) and are what
the `features` step of 18.4 hands to a belief.

**The sensor budget and its penalty** (rulings R235 and R281). `diet_cost_units(genome) =
sum(SENSORS[s].cost_units for s in genome.sensors)` is the diet's cost **per bar** and is `17` for the
full catalogue. `RULE_PROPOSAL_COST_UNITS = 1` is what one `propose_rule` costs on the bar it is made
(18.2), and `SENSOR_BUDGET_UNITS_DEFAULT = 18` is the two together, so **the shipped roster can
propose**: the default allowance constrains nothing until the penalty below bites, which is what the
first evolution measures against, and an arithmetic under which every v1 archetype was permanently
barred from proposing would have deleted one of PRD v5's three authors in silence.
`EvolutionConfig.sensor_budget_units: int = SENSOR_BUDGET_UNITS_DEFAULT` is the per-generation allowance
of a fresh genome and a per-bar cap; `RunConfig.sensor_budget_units: int = SENSOR_BUDGET_UNITS_DEFAULT`
and `RunConfig.sensor_budget_by_agent: tuple[tuple[str, int], ...] = ()` (sorted by `agent_id`, the
scalar's override, exactly the shape `research_budget_by_agent` has, 8.1) carry that allowance into the
run, because the runner and not the optimizer is what applies a per-bar cap. An agent's diet must
satisfy `diet_cost_units <= allowance`: `run_backtest` raises `InvalidConfigError` when it does not,
because the cull belongs to O2 at generation close (below) and a runner that silently drops an agent
loses a row nobody can find afterwards. The allowance is
per agent and shrinks by the generalised research-penalty rule of 12.6: an agent whose `skill_lb_micro` did
not improve over its own previous generation **and** whose `diet_cost_units > 0` gets
`max(0, allowance - SENSOR_PENALTY_UNITS)` (`SENSOR_PENALTY_UNITS = 2`, a default the first evolution
reports against) next generation; every other agent keeps `config.sensor_budget_units`. The result is
`generation_closed.sensor_budget_next {agent_id: units}` (9.4). When a child's diet exceeds its
allowance, O2 applies the **sensor drop** (`structural_mutate`, `op = "sensor_drop"` in
`generation_closed.children`): drop the most expensive sensor that is neither `tape` nor required by the
genome's families, ties by name descending, until the diet fits; a genome that cannot fit (its required
sensors alone exceed the allowance) is culled and the cull is recorded as `culled_by_budget` in
`generation_closed`. Money is money: fitness is **net of nothing**, a sensor cost is never a cash
movement and never reaches a journal cent (PRD v5 section 7); what a rich diet without skill loses is
its allowance, so it dies. `candidate_scored` gains `diet_cost_units: int` and `sensors: list[str]`, so
the diet an evaluation ran under is on the record beside its score.

**The diet descriptor** (12.5, ruling R235). `Descriptors` gains `diet_class: int` in `0..2`: `0` when the
diet carries no news sensor and no hive sensor (a tape, volume or cross-asset reader), `1` when it carries
at least one news sensor (`wiki_daily`, `comments`, `hn`, `gdelt_recent`, `filings`, `macro_releases`,
`wiki_asof`) and no hive sensor, `2` when it carries `hive_insights` or `hive_reputation`. It is a fourth
archive axis with three bins, so `ARCHIVE_CELLS = 4 * 4 * 3 * 3 = 144` and `cell_key =
f"t{i}-c{j}-a{k}-d{l}"`. **AC-6 is a rate over the reachable cells, not 40 percent of 144** (ruling
R297): `ARCHIVE_CELLS_REACHABLE = 48 * (the distinct diet_class values among the genomes scored at the
engine tier of the run)`, and AC-6's "at least 40 percent" is 40 percent of that, both numbers reported
side by side in the evolution's summary. The axis is degenerate at generation 0 by construction, since
the eight v1 archetypes all carry the full diet and therefore all sit in `d2`, so a flat 58 would treble
the target by arithmetic on an axis nothing had yet moved; the rate reads 20 cells at generation 0,
exactly the bar AC-6 had on three axes, and rises to 58 only once sensor mutation has produced all three
diet classes at the engine tier. 14.1's decision D-7 records the axis as amended.

**The sensor ablation** (PRD v5 section 5, AC-5 as gate G4 reads it). `pmx evolve --ablate-sensors` and
O4's `claim --ablate-sensors` re-run the champion once per sensor of its diet with that sensor removed
(`tape` excepted), each a run with its own run id (the genome differs, so `genome_hash` and the run id
differ), and report `skill_drop_micro` per sensor as the difference of the two `results.json` skill
intervals' points, never of two hashes (9.2's AC-5 rule); the claim record carries the table as
`sensor_ablation: [{sensor, run_id, skill_point_micro, skill_drop_micro}]`, and `GET
/claims/{claim_id}` serves it. A sensor whose removal changes no forecast is a sensor the agent paid for
and did not read, which is the measurement the budget rule acts on.

### 18.2 The hypothesis layer: rules, families, promotion, insights

**The record** (`pmx.rules.rule`, S2; `src/pmx/schemas/rule.v1.json`, C1c; fixture
`tests/fixtures/contract/rule.sample.json`):

```python
RULE_PREDICATES_MAX = 3                  # PRD v5 2.2: conjunctions of up to three predicates, every author alike
PREDICATE_OPS = ("lt", "le", "gt", "ge", "eq", "ne")
CLAIM_KINDS = ("bias", "drift", "volatility")
RULE_MIN_SUPPORT_DEFAULT = 30            # matched (market, bar) rows on the fit fold, a default the first build reports against

@dataclass(frozen=True, slots=True)
class Predicate:
    feature: str                   # one of pmx.rules.vocabulary.FEATURE_NAMES (the sensor blocks of 18.1)
    op: str                        # one of PREDICATE_OPS
    value: int                     # in the feature's unit, inside [lo, hi] of its FeatureSpec

@dataclass(frozen=True, slots=True)
class RuleScope:                   # where the rule claims to hold; every tuple sorted, () meaning "any"
    kinds: tuple[str, ...]; providers: tuple[str, ...]; categories: tuple[str, ...]
    tags: tuple[str, ...]; cohorts: tuple[str, ...]        # cohort ids of 18.5 (D-S7)

@dataclass(frozen=True, slots=True)
class RuleClaim:
    kind: str                      # one of CLAIM_KINDS
    direction: int                 # -1 | 1 for bias and drift ("the price is too high" is -1); 0 for volatility
    magnitude_bp: int              # bias, drift: basis points of the payout on a binary, bp_ratio of the price
                                   # on a continuous kind; 0 for volatility
    factor_ppm: int                # volatility: realised absolute move over the fit fold's median, PPM_ONE = usual;
                                   # 0 for bias and drift

@dataclass(frozen=True, slots=True)
class Rule:
    rule_id: str                   # "ru-" + sha256(canonical_json([scope, condition, claim, horizon_bars, min_support]))[:16]
    author_kind: str               # "agent" | "miner" | "detector"
    author_id: str                 # an agent id, "miner", or a detector id of 16.4
    born_at_ms: int                # the bar at which it was proposed (a bar open of the proposing run)
    scope: RuleScope
    condition: tuple[Predicate, ...]     # 1..RULE_PREDICATES_MAX, sorted by (feature, op, value), no duplicate feature+op
    claim: RuleClaim
    horizon_bars: int              # 0 for bias (measured at resolution); >= 1 for drift and volatility
    min_support: int               # >= RULE_MIN_SUPPORT_DEFAULT
    family_id: str | None          # the pre-registered family it was tested under (None until registered)
    def to_dict(self) -> dict[str, object]: ...
    def fires(self, blocks: Mapping[str, SensorBlock], meta: MarketMeta) -> bool: ...   # scope and every predicate
    def readable_by(self, sensors: Sequence[str]) -> bool: ...   # every predicate's feature is in those sensors' blocks
```

Rules are data, never code: a rule is evaluated on any bar of any dataset by `fires`, which reads the
sensor blocks of that bar and the market's `MarketMeta` (its `kind`, `provider`, `category`, `tags`, its
cohort of 18.5) and nothing else, so the same rule is testable on every fold, every grid and every
provider.

**Whose blocks** (ruling R279). `fires` reads **only the blocks it is handed** and is total: a rule whose
condition names a feature of a sensor absent from `blocks` does not fire, and `fires` never raises
`SensorAbsentError`. `readable_by(sensors)` is the predicate the hive view (10.4) and the `rules` step
(18.4) apply **before** evaluation, so an unreadable insight is never considered rather than silently
counted as not firing. The runner fills `Hive.view(..., blocks=)` from the agent's **own** sensed
observation, so an agent sees exactly the insights its diet can read: **what is not sensed is not seen**
holds for a rule as it holds for a field, and an agent that did not buy `hn` cannot be moved by a rule
about Hacker News. The **tester** has no agent and always evaluates against the whole catalogue's blocks,
so a rule's ledger interval is a full-diet statement and means one thing for everybody; `InsightView`
carries `required_sensors: tuple[str, ...]` so an agent, a chart and a claim can each see which of the
promoted rules a diet cannot read. A1's or A3's test hands a diet-restricted agent a promoted rule on a
feature outside its diet and asserts an empty `insights` tuple, never an exception.

`rule_id` is content-derived (`"ru-" + sha256(canonical_json([scope.to_dict(), [p.to_dict() for p in
condition], claim.to_dict(), horizon_bars, min_support]))[:16]`, the dict forms of `rule.v1.json`, so the
fixture's id recomputes from its own fields, asserted) and author-independent: two authors proposing the
same statement produce one rule, whose `author_id` is the first proposal's in journal order and whose ledger row counts
`n_proposals`. A predicate on a feature outside `FEATURE_NAMES`, an operator outside `PREDICATE_OPS`, a
value outside the feature's bounds, a fourth predicate, a `horizon_bars` of `0` on a drift or a
volatility claim, or a `magnitude_bp` of `0` on a bias or a drift claim is refused by `Rule.__post_init__`
and by `genome_from_dict`'s neighbour `rule_from_dict` with `RuleRefusedError` (13.1, ruling R236). A rule
never names a bar count, a fold, an outcome or any field of 7.9: its predicates are as-of by construction
because the blocks are, and the tester refuses a predicate on any name not in the catalogue.

**What a claim measures.** For a matched `(market, bar)` row (the rule fires at bar `t` on market `m`):

| Claim | Realised measurement `y_row` (an integer) | Unit |
|---|---|---|
| `bias(direction, magnitude_bp)` | `direction * (outcome_bp - price_bp(t))` on a binary, where `outcome_bp` is `BP_ONE * resolution`; on a continuous kind `direction * bp_ratio(price_{t+h} - price_t, price_t)` with `h` the shortest declared horizon | bp |
| `drift(direction, magnitude_bp, horizon_bars)` | `direction * (price_{t+h} - price_t)` on a binary (bp); `direction * bp_ratio(price_{t+h} - price_t, price_t)` otherwise, `price_{t+h}` the close of the `h`-th completed bar after `t`, rows with no such bar before `bar_of(resolved_at_ms)` skipped | bp |
| `volatility(factor_ppm, horizon_bars)` | `abs(price_{t+h} - price_t)` (bp, or `bp_ratio` on a continuous kind) minus `usual_bp`, where `usual_bp` is the median of the same quantity over **every** row of the fit fold in the rule's scope (matched or not), computed once per `(scope, horizon)` and recorded in the test record | bp |

The rule's **effect** is the block-bootstrap `Interval` (12.4) of the mean of `y_row` over the matched rows,
with `blocks` from `block_key` (event key, cluster or week) and `rng` from the tester's `RngTree`
(`stats.bootstrap`); `support` is the number of matched rows and `n_markets` the distinct markets among
them; `lift_bp` is the interval's `point`. A claim **holds** on a fold iff `support >= min_support`,
`n_markets >= RULE_MIN_MARKETS = 5` (a default), and `interval.lower > 0`. The statement "the price is
off by about `magnitude_bp`" is recorded and displayed but is not what is tested: the sign is (a rule
with the right direction and a magnitude off by half is a useful rule, not a false one), and the
magnitude is re-estimated on every fold as `point`.

**Who proposes** (ruling R237). Three authors, one ledger:

- **The symbolic miner** (`pmx.rules.miner`, S2; `pmx rules mine`): deterministic beam search on the
  **fit fold** over conjunctions of up to `RULE_PREDICATES_MAX` predicates, thresholds drawn from the
  feature's quantiles at `RULE_THRESHOLD_QUANTILES_PPM = (100_000, 250_000, 500_000, 750_000, 900_000)`
  over the fit fold's rows in scope, beam width `RULE_MINER_BEAM = 32`, at most
  `RULE_MINER_CANDIDATES_MAX = 10_000` candidates enumerated per family, scored by `lift_bp` with the
  support floor, ties broken by the canonical order of the predicate tuple. No randomness: the miner draws
  from no substream and two runs on one dataset produce one candidate list. Every candidate enumerated
  counts toward its family's `n_candidates`, whether or not it reaches the bootstrap.
- **An agent**: `Actions.propose_rule: RuleProposal | None` (8.4), at most one per agent per bar
  (`RULE_PROPOSALS_PER_BAR_MAX = 1`), validated by `rule_from_dict` and journaled as `rule_proposed`
  (9.2) with `author_kind = "agent"`; a scripted family proposes from its own parameters when its
  memory's `FeatureStat` for the effect has `n >= min_support` and a sign it has held for
  `RULE_PROPOSE_STABLE_BARS = 20` bars (A1 records the per-family rule); an LLM agent writes the record
  in the vocabulary, and a proposal that fails validation is `action_rejected(scope="rule",
  reason="bad_rule")`. Proposing costs the diet: an agent that proposes in a generation carries
  `n_rules_proposed` in `candidate_scored`, and a proposal costs `RULE_PROPOSAL_COST_UNITS = 1` sensor
  unit of that bar against the same cap (`diet_cost_units + RULE_PROPOSAL_COST_UNITS <= allowance` on a
  proposing bar, which the full diet meets because `SENSOR_BUDGET_UNITS_DEFAULT` is `18`, ruling R281),
  which is what "proposing costs sensor budget" means in integers. A proposal on a bar whose allowance
  cannot pay for it is `action_rejected(scope="rule", reason="budget_exceeded")` (8.4) and the genome
  keeps running: a refused proposal is a refused action, never a dead agent. **A proposer cannot flood a
  family** (ruling R300): `RULE_PROPOSALS_PER_GENERATION_MAX = 20` per agent bounds every author the way
  `RULE_MINER_CANDIDATES_MAX` bounds the miner (a proposal above it is the same
  `action_rejected(scope="rule", reason="budget_exceeded")`), and a rule that differs from one already
  tested in the same family only in a threshold still counts in `n_candidates` and still enters the
  family's `m`, so perturbing a value by one unit buys a proposer nothing but a harder FDR bar. Both
  numbers are defaults the first evolution with rules reports against.
- **A detector** (16.4): every `OpportunityEvent` of `news_lead`, `divergence`, `logic`, `comparative` and
  `cross_domain` that its detector can state as a `Rule` in the vocabulary is emitted as one, with
  `author_kind = "detector"` and `author_id` the detector id, into the same ledger and through the same
  tester; a finding that cannot be so stated stays an `OpportunityEvent` only and says so in its
  `evidence`. Hand-written and discovered knowledge are therefore compared on one footing.

**How a rule is tested and promoted** (decision D-R8, ruling R238). The tester (`pmx.rules.tester`, S2)
is a projection of the dataset and of the journals that proposed the rules; it never writes a **backtest**
journal, never reads the sealed fold (**architecture rule 3** binds `pmx.rules` exactly as it binds
`pmx.analysis`) and refuses a `purpose: "showcase"` dataset with `ShowcaseDatasetError` (12.7).
**Architecture rule 8 does not extend to `pmx.rules`** (ruling R294): the tester is the one emitter of
`family_registered`, `rule_tested`, `rule_promoted` and `rule_demoted` (9.3), so it imports `pmx.journal`
and writes those four into the evolution journal `optimizer/evolution.py` hands it and into its own
ledger. Rule 8 keeps `analysis/` on the projection side of the line and says so about `analysis/` alone;
a tester that could not name a `Journal` could not have written the four events 9.3 assigns to it, and
gate G4's E2E-5a reads them there.

1. **Pre-registration.** Before the tester reads a single row of the replicate fold, every rule of a
   generation is assigned to a **hypothesis family**, and the family is written down:

   ```python
   @dataclass(frozen=True, slots=True)
   class HypothesisFamily:
       family_id: str                 # "hf-" + sha256(canonical_json([dataset_hash, generation, fit_fold,
                                      # replicate_fold, registered_at_ms, fit_t1_ms, template]))[:16] (ruling R284)
       dataset_hash: str              # the dataset the family was drawn and tested on
       generation: int                # 0 for a standalone `pmx rules` run, else the evolution generation
       fit_fold: str                  # "train" or f"m1..m{k}": the fold the template was drawn and screened on
       replicate_fold: str            # "validation" or f"m{k+1}": the fold the FDR step and the replication read
       template: FamilyTemplate
       n_candidates: int              # every rule enumerated or proposed under the template, journaled
       n_screened: int                # the candidates whose claim held on the fit fold and were submitted to replication
       fit_t1_ms: int                 # the replicate fold's last bar: the visibility anchor of every promotion of this family (step 6)
       registered_at_ms: int          # the fit fold's last bar (the data the template was drawn on)
   @dataclass(frozen=True, slots=True)
   class FamilyTemplate:              # the grammar of a family: what may vary and what is fixed
       scope_keys: tuple[str, ...]    # subset of ("kinds", "providers", "categories", "tags", "cohorts") whose values vary
       features: tuple[str, ...]      # the predicate features, 1..RULE_PREDICATES_MAX, sorted (operators and thresholds vary)
       claim_kind: str; horizon_bars: int
       author_kind: str               # "agent" | "miner" | "detector": agent proposals of one generation are one family per template
   ```

   A family is registered by a `family_registered` event (9.4, phase `generation`; in a standalone run,
   the first line of the family's ledger file) **before** any `rule_tested(stage="replicate")` of its
   rules, and the tester refuses (`RuleRefusedError`) to replicate a rule whose family has no earlier
   `family_registered` in the same journal or ledger. `n_candidates` is the family's whole count on the
   fit fold, journaled, whatever happened to them. **The id names the data, not only the grammar**
   (ruling R284): without `dataset_hash`, `fit_fold`, `replicate_fold` and the two instants, `pmx rules
   test --rolling 4`, `--rolling 5` and `--headline` on one dataset would register three families under
   one `family_id` with three different `n_candidates`, the pre-registration guard would be satisfied by
   the wrong registration, and `m` and `k` on a `rule_tested` row would be unreadable. Every
   `families.jsonl` and `rules.jsonl` line carries `dataset_hash`, `fit_fold` and `replicate_fold`, which
   is exactly the key the duplicate rule of step 4 is defined on.
2. **The fit-fold screen.** Every candidate's claim is measured on the **fit fold** (18.2's table).
   Candidates whose claim does not hold are `rule_tested(stage="fit", passed=false)` and stop;
   the survivors are `n_screened` and are the hypotheses of the family's FDR step.
3. **False discovery rate control within the family** (Benjamini-Hochberg at `FDR_Q_PPM = 50_000`, five
   percent). Each screened rule receives a one-sided `p_value_ppm` on the **replicate fold** from
   `rule_permutation_p_ppm` (12.4, ruling R282), **the rule path's own null**, on the same statistic the
   promotion tests: the mean of `y_row` over the matched rows. It takes the fold's rows in the rule's
   scope, permutes the firing labels **within each block** (so each block keeps the number of rows the
   rule matched in it), recomputes the mean over the matched rows, and returns
   `p_value_ppm = round_half_up(PPM_ONE * (b + 1), permutations + 1)` where `b` counts the permutations
   whose mean reached the observed one. The `(b + 1) / (B + 1)` estimator is the point: a permutation
   test may not report `p = 0`, and a `p` that can only be `0` or a multiple of `1 / B` cannot be
   compared against a Benjamini-Hochberg threshold of `k * q / m`. The shuffles are drawn from
   `stats.permutation` and the effect's bootstrap from `stats.bootstrap`, the **registered** substreams of
   6.3 (ruling R282: the tester adds no substream of its own, because adding a name means adding it to
   `pmx.rng.SUBSTREAMS` in the same commit and these two shuffles are statistics, run inside
   `pmx.metrics.stats` where the two names already live). The count follows the family:
   `permutations = min(RULE_PERMUTATIONS_MAX = 20_000, max(RULE_PERMUTATIONS_MIN = 200, 20 * n_screened))`,
   which is the resolution the `k = 1` threshold needs at `q = 0.05`. A family whose `n_screened` exceeds
   `RULE_PERMUTATIONS_MAX * FDR_Q_PPM // PPM_ONE = 1_000` is **refused rather than tested**
   (`RuleRefusedError`, `reason = "family_too_large"`): a family nobody can resolve is a family the
   miner must split by template, not one to report a coin flip on.
   `benjamini_hochberg(p_values_ppm: Sequence[int], *, q_ppm: int = FDR_Q_PPM) -> tuple[bool, ...]`
   (12.4, E4's name, applied by S2 by the agreement recorded in section 13) sorts the `m = n_screened`
   p-values ascending, finds the largest `k` with `p_(k) * m <= k * q_ppm`, and rejects the null of every
   rule with `p <= p_(k)`; when no `k` exists nothing passes. The rule's `rule_tested(stage="replicate")`
   carries `p_value_ppm`, `permutations`, `m`, `k` and `fdr_passed`. `permutation_null` (12.4) is the
   **claim** path's null and is not called here: its arguments (`market_prices`, `outcomes`, `weights`
   pinned to `bar_weights_ms`) have no meaning for a rule's matched `(market, bar)` rows, and it scores a
   Brier skill against the market, which would fail a rule whose direction is right and whose
   `magnitude_bp` is off by half, the very rule 18.2 says is useful.
4. **Out-of-time replication is the primary criterion.** A rule is **promoted** iff its claim **holds on
   the replicate fold** (`interval.lower > 0` with the fold's own support and market floors) **and**
   `fdr_passed`. A rule that passes the FDR step and fails replication (or the reverse) is
   `rule_tested(stage="replicate", passed=false)` with every number recorded, status `rejected`; it is
   never an `Insight`, it keeps counting in its family, and the same content re-proposed later on the
   same `(dataset_hash, fit, replicate)` pair is a duplicate the tester refuses to re-test
   (`RuleRefusedError`, `reason = "duplicate"`), so nobody re-rolls a rejected rule. A negative result is a
   first-class ledger row.
5. **The folds a promotion may read.** The tester takes a pair of disjoint chronological folds
   `(fit, replicate)` from 12.7: **the rolling pair** `(months 1..k, month k+1)` (`pmx rules test
   --rolling k`, the pair every evolution generation uses), or **the headline pair** `(train, validation)`
   (`pmx rules test --headline`, used by L1 and by the claim path). **`k` is an explicit argument drawn
   from the pairs `Folds.rolling` holds, and the evolution uses the largest of them** (ruling R277):
   `Folds.rolling` holds the pairs for `k` in `4..9` **whose month `k + 1` ends at or before
   `train_end_ms`** and no others, so it may hold fewer than six and a rolling replicate month can never
   be a validation or a sealed month. Under the count quantiles of R247 the calendar position of
   `train_end_ms` is data-dependent, so an unclipped `for k in 4..9` would have replicated rules on the
   sealed fold on any distribution whose resolutions bunch early. `fit_t1_ms` is the last bar of the
   replicate fold, and the promotion **never reads a bar after it**. The sealed fold is never read by the
   tester (rule 3).
6. **Visibility follows the data** (10.4, ruling R239). A promoted rule enters the hive as an `Insight`
   with `visible_from_ms = fit_t1_ms + interval_ms`: the first bar strictly after the last bar its
   promotion read, mirroring the resolution release of 5.4. A rule promoted on the headline pair is
   therefore visible in the sealed fold and in the live book only; a rule promoted on the rolling pair at
   `k` is visible from the first bar of month `k + 2` of the training fold, so `rule_follower` and the
   families that take insights as priors can use it inside evolution on bars its promotion never saw.
   PRD v5 2.3 step 3 ("`visible_from = now + one bar`") and E2E-5a's sentence ("promotion on validation,
   an agent trades the promoted rule ... on validation") are corrected in place to this rule (ruling
   R238): the E2E fixture promotes on the rolling pair and trades on the validation fold, out of time.
7. **The live record and demotion.** After promotion the rule is scored at every later bar where it
   fires, on the same measurement, by the tester at each generation close and by L1 daily:
   `live_support`, `live_interval` (block bootstrap). **The live record is as-of** (ruling R276): at any
   bar `b` it covers the matched rows with `fit_t1_ms + interval_ms <= t < b`, and the value that reaches
   an `Insight` payload, an `InsightView` or a chart at `now_ms` is the one last recomputed at a bar at or
   before `now_ms`. The tester recomputes it at each generation close with `b` the generation's last
   completed bar, and L1 daily over `live/` rows with `b` the last live bar; the tester reads no sealed
   bar at any `b` (rule 3). "The rows after `fit_t1_ms`" without an upper bound would have run to the end
   of the dataset, so an agent trading month `k + 2` would have seen an insight demoted by what happened
   in month 11, which is exactly the field 7.9 forbids ("a rule's live record beyond `now_ms`"); freezing
   the record at the replicate fold's edge instead would have been worse, since a record that never grows
   can never demote a rule that decays. A rule is **demoted** (`rule_demoted`, the `Insight` gains
   `demoted_at_ms` and stops firing in views from the next bar) when, at the recomputing bar,
   `live_support >= RULE_LIVE_MIN_SUPPORT = 30` and `live_interval.upper < 0`, or when its author's
   reputation in the rule's dominant category falls below `0` while `live_interval.lower <= 0`. A demoted
   rule is never re-promoted by re-testing; a new proposal with the same content is a duplicate.
8. **Knowledge transfer** (PRD v5 section 5). Every promoted rule is re-tested by the same procedure on
   every other provider, category and kind of the dataset outside its scope, one `rule_tested(stage=
   "transfer", target=...)` per target, and the ledger records where it held and where it did not;
   a transfer test never promotes anything and never widens a scope. **It reads the promotion's own
   replicate fold, restricted to the targets outside the scope, and no bar at or after `fit_t1_ms +
   interval_ms`** (ruling R276): the transfer test is a re-test of a promoted rule, not a licence to walk
   forward into the validation and sealed months a rule's promotion never read.

**The `Insight`** (10.4, A3): `HiveEntry(kind="insight", author_id=rule.author_id, market_id=None,
written_at_ms=promotion bar, visible_from_ms=fit_t1_ms + interval_ms, payload={rule: Rule.to_dict(),
test: {fit: Interval, replicate: Interval, p_value_ppm, fdr_m, fdr_k, family_id}, live: {support,
interval}, demoted_at_ms: int | None})`, journaled as `hive_written(kind="insight")`.
`HiveView.insights: tuple[InsightView, ...]` carries, for the agent's open markets, the promoted and
undemoted insights **the agent's diet can read** (`rule.readable_by(observation.sensors)`, ruling R279)
**and whose rule fires at `now_ms`** on that market (`InsightView(rule_id, market_id, claim, lift_bp,
lower_bp, upper_bp, live_support, required_sensors, author_id, author_skill_micro)`), ranked by
`(-lower_bp, rule_id)`, at most `limits.hive_insights = HIVE_INSIGHTS_VIEW_MAX = 50`; the view is a pure
function of `(now_ms, agent_id, market_ids, the blocks of this bar)` and never depends on the order
agents are served in. `Hive.write_insight(*, rule: Rule, test: Mapping, fit_t1_ms: int, interval_min:
int) -> HiveEntry` and `Hive.demote_insight(*, rule_id: str, bar_ms: int) -> HiveEntry` are the two
writers, both engine-only (O2 at generation close through the hive snapshot of 9.5, L1 daily). The
poisoning test of 10.4 gains a false insight from an author with negative reputation and asserts it ranks
last and never fires above a true one.

**The author's reward** (12.6, ruling R239). At every generation close, for every rule promoted this
generation whose `author_kind == "agent"`, the author receives `RULE_AUTHOR_BONUS_MICRO = 5_000` added
to its `skill_lb_micro` **for ranking only** (never to the recorded interval, never to a claim) and
`RULE_AUTHOR_SENSOR_BONUS_UNITS = 2` added to its next allowance; for every rule of the author demoted
this generation, or rejected at the replicate stage, the author's next allowance loses
`SENSOR_PENALTY_UNITS`. `generation_closed` carries `rule_rewards: [{agent_id, rule_id, kind:
"promoted" | "rejected" | "demoted", skill_bonus_micro, sensor_units}]`. The three numbers are defaults
the first evolution with rules reports against.

**The ledger on disk.** `rules/<dataset_hash[:8]>/families.jsonl` and `rules/<dataset_hash[:8]>/
rules.jsonl`, **tracked** like `claims/` (12.7: the ledger is evidence), one canonical line per
`family_registered`, `rule_tested`, `rule_promoted` and `rule_demoted` event, appended by the tester
whether it runs inside an evolution (where the same events also enter the evolution journal) or
standalone; each line carries `dataset_hash`, `fit_fold` and `replicate_fold` (ruling R284), and
`prev_sha256` chains the file as claims are chained. **The tester never writes a `rule_proposed` line of
its own** (ruling R294): `rule_proposed` has one emitter, `engine/runner.py` (9.3), and `pmx rules ledger`
copies those rows out of the run journals into the ledger it renders, so one event kind keeps one writer. `pmx rules ledger` renders it; `GET /rules` and `GET /rules/{rule_id}` (12.12) serve it.

### 18.3 Minute grids and the timestamped-sources rule

**The third grid** (5.1, 5.2, ruling R241). `INTERVALS_MIN = (1, 60, 1_440)`; `bar_of`, the density rule
and the one-grid-per-run rule are unchanged; a minute dataset is a **separate dataset** with its own hash,
folds and claims, exactly as an hourly one is (7.8). A minute bar opens at a multiple of `MS_PER_MINUTE`;
`bars_window` is the caller's and `BARS_WINDOW_MAX = 720` (twelve hours of minute bars) is unchanged.
Minute datasets are built per instrument on demand for the event studies and the minute agents, never for
the evolution of a whole population (PRD v5 section 7): `pmx data build --interval-min 1` requires an
explicit instrument or series list and refuses a bare provider. **The list has a field** (ruling R298):
`BuildConfig` gains `instruments: tuple[str, ...] = ()` (sorted, unique, the vendor symbols of 17.1 the
build imports), and `BuildConfig.__post_init__` raises `InvalidConfigError` when `interval_min == 1` and
both `instruments` and `kalshi_series_allow_list` are empty. **On a minute build the allow-list is an
input and not a debug narrowing**, which is the one exception to ruling R258's rule that the series list
is an output: a minute build has no universe walk to derive a list from, because it is built for a named
instrument or a named series and for nothing else.

**Which sources may enter which grid.** Every news source carries a granularity and a default lag in
`pmx.types`:

```python
SOURCE_GRANULARITY_MS = {"wikipedia_current_events": MS_PER_DAY, "wikipedia_asof": MS_PER_DAY, "wayback": MS_PER_DAY,
                         "cboe": MS_PER_DAY, "gdelt": 15 * MS_PER_MINUTE, "manifold_comment": 1, "hn": 1_000,
                         "edgar": 1_000, "fred": 1_000}
SAFETY_LAG_MS_BY_SOURCE = {"wikipedia_current_events": SAFETY_LAG_MS_DEFAULT, "wikipedia_asof": SAFETY_LAG_MS_DEFAULT,
                           "wayback": SAFETY_LAG_MS_DEFAULT, "cboe": SAFETY_LAG_MS_DEFAULT, "gdelt": 15 * MS_PER_MINUTE,
                           "manifold_comment": MS_PER_MINUTE, "hn": 5 * MS_PER_MINUTE, "edgar": MS_PER_MINUTE, "fred": 0}
MINUTE_SOURCE_GRANULARITY_MAX_MS = 15 * MS_PER_MINUTE
```

A source enters a dataset with `interval_min = 1` iff `SOURCE_GRANULARITY_MS[source] <=
MINUTE_SOURCE_GRANULARITY_MAX_MS` (Hacker News, GDELT recent, Manifold comments, SEC filings, ALFRED
releases; **never** a Wikipedia day page, a Wayback capture or a daily VIX print), and
`BuildConfig.__post_init__` refuses a `news_sources` entry that fails it with `InvalidConfigError`: a
minute dataset never carries a source whose timestamp is coarser than fifteen bars of its grid, because an
item stamped to a day and lagged six hours is indistinguishable from one hundred and eighty minute-items
and every minute hypothesis on it is a hypothesis about the stamp. Daily and hourly datasets admit every
source (D-R5: the day pages stay in the daily and hourly datasets). **A sensor whose sources are partly
inadmissible keeps the admissible ones** (ruling R287): `macro_releases` on a minute dataset carries
`fred` and not `cboe`, the builder lists what it dropped and why in `manifest.news.sources`, and the
sensor's derived `granularity_ms` and `lag_ms` (18.1) are recomputed over the sources the dataset
actually carries, so the catalogue a minute run records is the catalogue it read. The lags are defaults the first
minute build reports against; `visible_from_ms = published_at_ms + lag(source)` where `lag(source)` is
`manifest.news.safety_lag_by_source[source]` when present, else `manifest.safety_lag_ms` (5.5, 7.3), and
the loader recomputes it per source and refuses a mismatch as it does today. Funding and liquidation
instants of a crypto venue are `CashEvent`s (17.3) and reach an agent through `MarketView.cash_events`
under `volume_profile`, never as news.

**Hacker News** (`pmx.data.news.hn`, F5): Algolia `search_by_date` with `numericFilters=created_at_i`
windows and `hitsPerPage` pagination through the one HTTP client of 7.11; a story is
`NewsItem(source="hn", kind="story", published_at_ms = created_at_i * 1_000)` with `points` and
`num_comments` in `text`'s first line as `points=<n> comments=<n>` and in the `hn` sensor block as
integer features (`hn_story_points`, `hn_story_comments`, `hn_mentions_subject`, `minutes_since_story`), a
comment is `kind="comment"`, subjects are matched through the linker of 7.6, and the news id code is `hn`
(18.7). `pmx.data.news.timestamped` (F5) is the one implementation of the admission rule above and of
the per-source lag, imported by the builder.

**The minute event study** (R2a, 16.4, ruling R242). On a minute dataset the news-lead detector runs at
`NEWS_LEAD_MINUTE_HORIZONS_BARS = (1, 5, 10, 30, 60)`, per source and per story feature (points band,
comment-count band, subject match), and emits its findings as **rules** (18.2, `author_kind =
"detector"`, `claim.kind = "drift"` or `"volatility"`, `horizon_bars` one of the five) into the ledger
beside its `OpportunityEvent`s, so "if a story of this type appears, watch the next ten minutes" is a
tested statement with an interval and a null, not a chart. AC-28's planted ten-minute drift is such a rule
with `interval.lower > 0` on the replicate fold.

### 18.4 Workflow genomes

**The genome** (10.1, A1, ruling R243). `Genome.workflow: Workflow | None`, always rendered by
`to_dict()`; `None` is the **degenerate linear case**: the graph `sense -> features -> belief(family)
[-> overlay(inner chain)...] -> sizing -> actions` derived from `(family, inner, members)` by
`pmx.agents.workflow.linear_workflow(genome)`, so every family and every composition of 10.5 is a valid
workflow and no genome hash of a linear genome depends on the graph (the key renders `null`). The
declaration document is `src/pmx/schemas/workflow.v1.json` (C1c); the fixture is
`tests/fixtures/contract/workflow.sample.json`.

```python
STEP_KINDS = ("sense", "features", "rules", "belief", "overlay", "sizing", "propose_rule", "llm_belief", "actions")
WORKFLOW_STEPS_MAX = 12; WORKFLOW_DEPTH_MAX = 8; WORKFLOW_WIDTH_MAX = 4      # defaults the first build reports against

@dataclass(frozen=True, slots=True)
class Step:
    kind: str                            # one of STEP_KINDS
    ref: str | None                      # belief/overlay/sizing: a family name of 10.5 with that role; rules: None;
                                         # llm_belief: the seat's model id; sense/features/actions/propose_rule: None
    params: tuple[tuple[str, int], ...]  # sorted by name: the family's genes for belief/overlay/sizing (10.1's ranges);
                                         # rules: min_lower_bp, weight_permille; propose_rule: stable_bars, min_support

@dataclass(frozen=True, slots=True)
class Workflow:
    steps: tuple[Step, ...]              # in topological order; steps[0].kind == "sense", steps[-1].kind == "actions"
    edges: tuple[tuple[int, int], ...]   # (from, to) with from < to, sorted; every step reachable from 0 and, propose_rule
                                         # excepted (it feeds nothing), reaching the last
    def to_dict(self) -> dict[str, object]: ...
        # {"steps": [{"kind", "ref", "params": {name: value}}, ...], "edges": [[from, to], ...]}: workflow.v1.json
```

**The bounds and the shape.** `len(steps) <= WORKFLOW_STEPS_MAX`; the longest path has at most
`WORKFLOW_DEPTH_MAX` steps; no step has more than `WORKFLOW_WIDTH_MAX` predecessors or successors;
exactly one `sense` (the source) and one `actions` (the sink); at least one `belief` or `llm_belief`; at
most one `sizing` and at most one `propose_rule`; `rules` takes its input from `features` and feeds a
`belief`, an `overlay` or `actions`; `propose_rule` hangs off a `belief` or a `rules` step and feeds
nothing (its output is `Actions.propose_rule`); `llm_belief` requires `needs_gateway` and obeys 11.3 (one
call per agent per bar, whatever the graph). `edges` with `from < to` over a topologically ordered
`steps` tuple is the canonical form, so two workflows that draw the same graph serialise to the same
bytes and `genome_hash` is defined once. `Workflow.__post_init__` refuses a breach with
`InvalidConfigError`. The sensor set of the `sense` step is the genome's `sensors` (18.1), never a
parameter of the step, so the diet has one home.

**Execution** (`pmx.agents.workflow.run_workflow`, A1; the signature is declared in 12.11, ruling R278,
because the runner must journal a per-step digest it can get from nowhere but this function's return
value). Each bar, in topological order, every step is a pure function of its predecessors' outputs and of
`(genome, memory view, rng)`: `sense` yields the
observation's sensor blocks (18.1); `features` the concatenated integer vector; `rules` the insights the
genome's diet can read (`rule.readable_by(genome.sensors)`, ruling R279) that fire on each market with
`lower_bp >= params.min_lower_bp`, folded into a per-market prior shift of
`sum(claim.direction * (lift_bp * weight_permille // 1_000))` bp over the firing insights whose
`claim.kind` is `bias` or `drift` (ruling R280: a `volatility` insight contributes **nothing** to a
belief and is available to a `sizing` step only); a `belief` yields `prob_ppm` per open market by its family's
rule of 10.5 (an inner chain of `overlay` steps transforms it); `sizing` yields `MarketAction`s by its
family (`kelly`) or by 10.5's default rule when absent; `propose_rule` yields at most one `RuleProposal`;
`actions` assembles the `Actions`. Two belief steps feeding one sizing step are combined by the
unweighted mean of their `prob_ppm` (the stacker's fallback rule), stated so nobody invents a weight.
Every step's inputs and outputs are integers; determinism and replay are unchanged.

**The journal** (9.2, rulings R243 and R278). For an agent whose `Genome.workflow` is not `None`, the
runner emits one `workflow_step_executed` per `(agent, bar, step)` in the `decide` phase, filled from the
`tuple[StepTrace, ...]` `run_workflow` returns beside the actions (12.11): `agent_id`, `step_index: int`,
`kind`, `ref: str | null`, `n_inputs: int`, `n_out: int` (the number of integers the step produced)
and `output_sha256: str` over `canonical_json` of the step's output; the payload is bounded by
construction (no output is journaled, only its digest) and there are at most `WORKFLOW_STEPS_MAX` per
agent-bar. A linear genome (`workflow: null`) emits none, so no journal of a v2 roster gains a byte.
AC-29 reads: a workflow genome with a `propose_rule` step runs, its steps are journaled, `pmx run
replay` rebuilds `results.json` byte for byte, and a structure mutation changes `genome_hash` and the
journal hash.

**Mutation** (10.1). Structure mutation (`structural_mutate`) adds a step of the catalogue, removes a
non-mandatory step, rewires one edge or swaps a `belief`, `overlay` or `sizing` family for another of the
same role, then re-canonicalises and re-validates; a result that breaches a bound is discarded and the
parent is returned unchanged (never a silent clamp). Parameter mutation acts inside a step exactly as
10.1's gene mutation does. The `op` of a structural child in `generation_closed.children` is
`"structural"` as today; `sensor_drop` (18.1) is the one new value.

### 18.5 The cohort

**The object** (decision D-S7, ruling R266; `pmx.cohorts`, DS2):

```python
COHORT_MIN_TRAIN = 30                         # usable at n_train >= 30 (D-S6, D-S7)

@dataclass(frozen=True, slots=True)
class Cohort:
    cohort_id: str                            # f"co-{provider}-{category}-{subject}-{structure}-{horizon}" (18.7)
    category: str; subject: str; structure: str; horizon: str; provider: str
    n_train: int; n_validation: int; n_sealed: int
    usable: bool                              # n_train >= COHORT_MIN_TRAIN
    usable_for_paired_test: bool              # usable and n_train > 0 and n_validation > 0 and n_sealed > 0 (D-S13)
    market_ids: tuple[str, ...]               # canonical order; in the loader's object, never in the manifest row
    def to_dict(self) -> dict[str, object]: ...   # the manifest row: every field but market_ids
```

A market belongs to **exactly one cohort**, keyed on its `provider`, `category`, **primary subject**
(`subject[0]`, the tagger's precedence order of 7.14), `structure` and `horizon`; a market whose
subject is `platform-meta` or whose `structure` or `horizon` is `other` belongs to no cohort
(`MarketMeta.cohort_id = None`). `pmx.cohorts.list_cohorts(metas) -> tuple[Cohort, ...]` is the one
implementation, sorted by `cohort_id`, and both the builder (into `manifest.cohorts`) and the loader
(into `Dataset.cohorts`) call it; `MarketMeta` gains `subject`, `structure`, `horizon`, `provider_labels`
and `cohort_id` as defaulted fields (7.2).

**A cohort is never a unit that moves a market between folds** (ruling R293). Unlike an `EventCluster` or
a Kalshi `event_key` group (R248), a cohort has **no fold of its own**: every one of its markets keeps the
fold 7.7 gave it, and `n_train`, `n_validation` and `n_sealed` are what those folds left. A cohort with a
zero in any of the three is `usable_for_paired_test = false` and is unusable for a paired bound or a
replication (D-S13). The loader refuses (`FoldIntegrityError`) a manifest whose cohort rows disagree with
the counts it recomputes from the folds. Reading "a cohort never crosses a fold" as the cluster rule would
pull every market of a dense Kalshi series into one fold and collapse the train fold onto the sealed one,
which is the opposite of what the cohort exists for: the three counts in this dataclass exist **because**
a cohort spans the folds.

**The unit of comparative analysis** (D-S7): detector `comparative` (R2d, 16.4) runs **per cohort**
and reports per-cohort intervals and nulls with the cohort size beside every number; the `calibrator`
family's ledger key gains the cohort (`(cohort_id or category, horizon_bucket, bin)`, 10.3, 10.5), so a
class of question systematically mispriced is a cohort-level statement; a rule's `scope.cohorts` (18.2)
names cohort ids and a hypothesis family may be keyed on a cohort (`scope_keys` containing `"cohorts"`),
whose `n_candidates` is journaled like any other family's; `LeaderboardRow` gains `cohort_id: str =
"all"` and 12.10 emits one row per usable cohort (`n_train >= COHORT_MIN_TRAIN`) with its own `skill` and
`pnl` intervals; a claim (12.8) gains `per_cohort: [{cohort_id, lexicon_version, n, n_traded, skill,
pnl, null, candidates, verdict}]`, one row per cohort of the dataset, each with its own `K`
(`candidates_prior_claims` counted per `(dataset_hash, cohort_id)`) and its own four-part verdict at the
same `CLAIM_MIN_MARKETS`. **There is no `pmx claim --cohort`** (ruling R283): a cohort statement is a row
of the one claim, made on the one sealed read that claim already paid for, and a per-cohort flag on the
claim command would have been a second bite at the same sealed markets under a `claim_id` that names no
cohort, either overwriting the first claim's file or being refused as an aborted peek. A cohort that is
not `usable_for_paired_test` gets a row with `verdict: "not_usable"`, its counts and no bounds, so the
reader sees the cohort was measured and why nothing was concluded. `CohortRefusedError` (13.1) is raised
by `pmx.cohorts.cohort_or_refuse`, by the per-cohort leaderboard of 12.10 and by the `comparative`
detector when asked for a cohort below `COHORT_MIN_TRAIN` or not `usable_for_paired_test`, before any
measurement and never weakened to a smaller bar. `GET /datasets/{name}/cohorts` and the cohort filters of
12.12 serve them.

**Why a tag cannot leak** (7.9). A facet, a provider label and a cohort id are data about the question that
exist before the market's first bar: they are computed from `question`, `provider_id` and the market's
declared life (`created_at_ms`, `close_at_ms`, which are public on every venue from listing), never from
`resolved_at_ms`, a bar or a resolution, and the tagger reads none of 7.9's fields (7.14). They may
therefore sit in a `MarketView` and in a rule's scope at every bar. `horizon` is derived from
`close_at_ms - created_at_ms`, the venue's published close, never from `resolved_at_ms`, for exactly this
reason.

**Which vocabulary a cohort was cut under is on the record** (ruling R301). A new `tags.vN` moves every
facet, therefore every `cohort_id`, therefore the `dataset_hash` (the lexicons are copied inside the walk,
7.14), so two claims cut under two vocabularies already differ in a field every claim carries. That is
enough for a machine and not enough for a reader comparing two `per_cohort` tables, so the
`manifest.taxonomy.version` a build tagged under (`tags.vN`, 7.8) is copied into every `per_cohort` row of
a claim as `lexicon_version`, and every cohort row of a leaderboard is read under the version its dataset
names. No second field is added to `Cohort` or to the manifest: the version exists once, in the manifest's
`taxonomy` block, and travels on the records a reader compares across datasets. The boundaries of
`horizon` (1 d, 7 d, 31 d, 183 d) and the tagger's precedence order are part of that version: moving
either is a new lexicon version and therefore a new dataset, never an edit to an existing one.

### 18.6 Evaluation additions

Three additions, each a projection of things already journaled: the **knowledge-transfer re-test** (18.2
step 8, on the promotion's own replicate fold and no bar after it, ruling R276; `rule_tested(stage=
"transfer")` rows in the ledger, `GET /rules/{rule_id}` serves them); the
**rule-adjusted claim** (12.8): a claim lists `rules_used: [{rule_id, live_support, live_lower_bp,
n_bars_fired}]`, the insights the agent's `rules` step or `rule_follower` genome read during the claim run,
with their live records **at claim time**, so a reader can tell an agent that learned from an agent that
followed a lucky rule; and the **sensor ablation** (18.1, the claim's `sensor_ablation` table and gate
G4's AC-5). The UI (U3, lot 7) shows the rule ledger (every rule, its author, its condition in words, its
test and live records, where it fires on a chart) and the ablation table, which is AC-30.

### 18.7 The module map, the architecture rule and the identifier formats of this amendment

Section 13 carries one owner per new file (ruling R245):

| File | Owner | What it is |
|---|---|---|
| `src/pmx/schemas/rule.v1.json`, `sensor.v1.json`, `workflow.v1.json` | C1c | this amendment's three schemas (18.2, 18.1, 18.4) |
| `src/pmx/sensors/__init__.py`, `src/pmx/rules/__init__.py`, `src/pmx/features/__init__.py` | C1c | docstring-only, created by this amendment (ruling R122: the amendment that opens a package's directory owns its `__init__`; `features/` is opened by FM1 in lot 6, before amendment C3) |
| `src/pmx/sensors/catalogue.py`, `src/pmx/sensors/<sensor>.py` (one module per sensor of 18.1) | S1 | `SENSORS`, `SENSOR_NAMES`, `CATALOGUE_HASH`, `SENSOR_BY_NEWS_SOURCE`, `SensorSpec`, `SensorBlock`, `sense`; `SensorAbsentError` added to `pmx.errors` and raised by E1's sensed views, by the agreement recorded in section 13 (ruling R232) |
| `src/pmx/rules/vocabulary.py`, `rule.py`, `tester.py`, `miner.py`, `src/pmx/cli_rules.py` | S2 | `FEATURE_NAMES`, `Predicate`, `RuleScope`, `RuleClaim`, `Rule`, `Rule.readable_by`, `rule_from_dict`, `HypothesisFamily`, `FamilyTemplate`, the tester and the miner of 18.2, `pmx rules mine|test|ledger`; `benjamini_hochberg` **and `rule_permutation_p_ppm`** added to E4's `pmx.metrics.stats` by the agreement recorded in section 13 (rulings R238 and R282) |
| `src/pmx/data/news/hn.py`, `src/pmx/data/news/timestamped.py` | F5 | Hacker News through Algolia, the admission rule and the per-source lag of 18.3 |
| `src/pmx/data/importers/binance.py` (the minute path) | F1 | 1-minute klines, funding and liquidation instants as `CashEvent`s (17.7's row, widened) |
| `src/pmx/data/builder.py`, `loader.py`, `universe.py`, `src/pmx/data/news/wikipedia_current_events.py`, `src/pmx/data/news/linker.py`, `src/pmx/cli_data.py` | DS1 | the fold fix (D-R1, D-R2), per-bullet timestamps (D-R3), the linker audit tooling (D-R4), the hourly headline build (D-R5), the documented universe rule (D-R7, D-R13), `window_days` and `purpose` (D-S3, D-S4); `data/universe.py` moves from R1a to DS1 and R1a's row reads "the statistics only" |
| `src/pmx/data/taxonomy.py`, `src/pmx/cohorts.py`, `src/pmx/lexicons/tags.v1.json`, `src/pmx/lexicons/kalshi_series_facets.v1.json`, `src/pmx/data/showcase.py` | DS2 | the tagger and the vocabulary of 7.14, `Cohort`, `list_cohorts` and `cohort_or_refuse` of 18.5, the showcase pack of D-S5; the two lexicon files are section 13's rows too (ruling R295), and `kalshi_series_facets.v1.json` never supersedes D2's `kalshi_series_subjects.v1.json`; the tagging and cohort-listing calls are added to DS1's `builder.py` and `loader.py` by the agreement recorded in section 13, against the signatures of 7.14 and 18.5 (the R1d precedent) |
| `src/pmx/features/matrix.py` | FM1 | the precomputed integer feature matrices of the proxy tier (12.6, D-R9) |
| `src/pmx/agents/workflow.py`, `src/pmx/agents/families/rule_follower.py` | A1 | `Workflow`, `Step`, `linear_workflow`, `run_workflow` (18.4); the `rule_follower` family of 10.5 |
| `src/pmx/metrics/capacity.py` | O4 | the capacity metric of 12.3 (D-R10), computed at claim time |
| `src/pmx/api/routes_rules.py`, `web/src/components/rules/**` | U1, U3 | the rule ledger and ablation routes of 12.12 and their views |
| `tests/test_sensors.py`, `tests/fixtures/s1/` | S1 | |
| `tests/test_rules.py`, `tests/fixtures/s2/` | S2 | the planted-effect fixture and its shuffled twin (AC-27) |
| `tests/test_hn.py`, `tests/fixtures/f5/` | F5 | |
| `tests/test_taxonomy.py`, `tests/test_cohorts.py`, `tests/test_showcase.py`, `tests/fixtures/ds2/` | DS2 | |
| `tests/test_feature_matrix.py` | FM1 | |
| `tests/test_workflow.py` | A1 | |
| `tests/e2e/test_e2e_5a_discovery.py` | gate G4 | PRD v5's E2E-5a, as corrected by ruling R238 |

**Rule 12 joins the eleven of `tests/test_architecture.py`** (ruling R245), green on the tree of
2026-09-09 where none of the files exists: **the tagger is never a model call.** Nothing under
`src/pmx/data/`, nor `src/pmx/cohorts.py`, nor `src/pmx/rules/`, nor `src/pmx/sensors/` imports
`pmx.gateway` or `pmx.llm`, and none of them opens a socket (rule 5 already binds the last). A tag decides
which cohort a market lands in and a rule decides what an agent trades; a tag or a rule that a model
wrote would move a claim between two rebuilds.

**Identifier formats**, the continuation of the tables of sections 2, 16.7 and 17.8 (ruling R246). Every
regex is a constant beside its owning module (ruling R121):

| Entity | Format | Regex | Assigned by |
|---|---|---|---|
| Sensor | lowercase name, one of fifteen | `^(tape\|microstructure\|volume_profile\|cross_asset\|calendar\|wiki_daily\|comments\|hn\|gdelt_recent\|filings\|macro_releases\|wiki_asof\|hive_insights\|hive_reputation\|memory)$` | this contract, `pmx.sensors.catalogue.RE_SENSOR` |
| Rule | `ru-<sha256(canonical_json([scope, condition, claim, horizon_bars, min_support]))[:16]>` | `^ru-[0-9a-f]{16}$` | `pmx.rules.rule.RE_RULE_ID` |
| Hypothesis family | `hf-<sha256(canonical_json([dataset_hash, generation, fit_fold, replicate_fold, registered_at_ms, fit_t1_ms, template]))[:16]>` (ruling R284) | `^hf-[0-9a-f]{16}$` | `pmx.rules.tester.RE_FAMILY_ID` |
| Cohort | `co-<provider>-<category>-<subject>-<structure>-<horizon>` | `^co-[a-z]+-[a-z]+-[a-z0-9-]+-[a-z-]+-[a-z-]+$` (at most 96 characters) | `pmx.cohorts.RE_COHORT_ID` |
| Rule author | an agent id, `miner`, or a detector id | `^([a-z][a-z0-9_]{0,31}(-[0-9a-f]{8})?\|miner\|news_lead\|divergence\|logic\|comparative\|cross_domain)$` | `pmx.rules.rule.RE_AUTHOR_ID` |
| Step kind | one of nine | `^(sense\|features\|rules\|belief\|overlay\|sizing\|propose_rule\|llm_belief\|actions)$` | this contract, `STEP_KINDS` |
| News item | `<source_code>-<yyyymmdd>-<idx:04d>` | `^(wce\|wasof\|wb\|gd\|mfc\|edg\|fred\|cboe\|hn)-[0-9]{8}-[0-9]{4}$` | F5; `hn` Hacker News |
| Facet value | lowercase slug from `tags.v1.json` | `^[a-z][a-z0-9-]{0,31}$` | DS2, 7.14 |

### 18.8 What amendment C1c does not own

C1c owns `docs/CONTRACTS_V2.md` (this section, 7.14, 15.10 and every in-place amendment recorded there),
the three new schemas, the widenings of `market.v2.json`, `news.v1.json`, `dataset.v1.json`,
`actions.v2.json` and `journal.v2.json`, `tests/test_contract_schemas.py`, `tests/test_architecture.py`,
the fixtures under `tests/fixtures/contract/`, the three `__init__.py` files of 18.7, and the sentences
of `docs/PRD_V2_HARD_OPTIMIZER.md` 6.1, `docs/PRD_V3_TRADING_OPTIMIZER.md` AC-11, `docs/PRD_V5_DISCOVERY.md`
2.3 and 6, and `docs/PLAN_V3_WAVES.md` part 4 that its rulings correct in place. Applied by this amendment in those files,
on the tree of 2026-09-09: `market.v2.json`'s four optional taxonomy fields and its `interval_min` of `1`;
`journal.v2.json`'s six declared events under `$defs` (outside `oneOf`), the optional
`observation_built.sensors`, `run_started.sensor_catalogue_hash`, `market_listed` facets, `candidate_scored`
and `generation_closed` fields, the `insight`, `rule` and `sensor_drop` enum values and the `genome`'s
`card`, `sensors` and `workflow`; `dataset.v1.json`'s optional `purpose`, `window_days`, `resolution_span`,
`split` cuts and moves, `news.safety_lag_by_source`, `news.linker_audit`, `universe`, `taxonomy`, `cohorts`
and `build` blocks, the `hn` source and the `taxonomy/` path prefix; `actions.v2.json`'s optional
`propose_rule`; `news.v1.json`'s `hn` source and `story` kind, `published_at_source` and the
revision-stamped `revid` of a `wce` bullet; `rule.v1.json`, `sensor.v1.json`, `workflow.v1.json` and their
three fixtures (`rule.sample.json`, `sensor.catalogue.json`, `workflow.sample.json`); the three
`__init__.py`; rule 12 in `tests/test_architecture.py`; and the PRD and plan sentences named above.
The arbitration of this amendment's own critic (rulings R276 to R302) applied, in the same files: the
`sentinel` field of `sensor.v1.json` and all seventy-five sentinels of `sensor.catalogue.json` with the
derived `granularity_ms` and `lag_ms` of `macro_releases` and a regenerated `catalogue_hash` (R285, R287);
`market_listed.cohort_id` in `journal.v2.json` (R288); the `audits/` path pattern in `dataset.v1.json`
(R296); and the assertions in `tests/test_contract_schemas.py` that pin the sentinel rule, the derived
pair, the new budget sentence, the cohort id and the ruling range. Two of those assertions pinned wording
this arbitration changed and were corrected with it, which is a test disagreeing with the contract and not
a weakening (R232's precedent). `news.v1.json`'s C1b widening (`edgar`, `fred`, `cboe`) stays gate G3b's as
17.9 says. **A section of this document is never a contract issue** (ruling R136), so every normative
passage this amendment changes is amended in place: 0, 5.1, 5.2, 5.5, 5.6, 7.1 to 7.4, 7.6 to 7.9, 7.13, 8.1 to 8.4, 8.6, 9.2 to 9.5, 10.1,
10.3 to 10.5, 11.5, 12.2 to 12.12, 13, 13.1, 13.2, 14, 14.1, 16.1, 16.3, 16.4, 16.5, 17.6 and 17.7. What
is left is code in a file another package owns, listed with the package that applies it:

| Issue | File and owner | Applied by |
|---|---|---|
| R230, R231, R235, R241, R243, R247, R262, R263, R265, R266: `INTERVALS_MIN`, `SOURCE_GRANULARITY_MS`, `SAFETY_LAG_MS_BY_SOURCE`, `MINUTE_SOURCE_GRANULARITY_MAX_MS`, `WINDOW_DAYS_MAX`, `COHORT_MIN_TRAIN`, `SENSOR_BUDGET_UNITS_DEFAULT`, `SENSOR_PENALTY_UNITS`, `SENSOR_COST_MAX`, `HIVE_INSIGHTS_VIEW_MAX`, `RULE_*` constants of 18.2, `STEP_KINDS`, `WORKFLOW_*` bounds, `FDR_Q_PPM`, `ARCHIVE_CELLS = 144`, `Descriptors.diet_class`, `RunConfig.sensor_catalogue_hash`, `Observation.sensors`, `Limits.hive_insights`, `HiveView.insights` and `InsightView`, `MarketMeta.subject`, `structure`, `horizon`, `provider_labels`, `cohort_id`, `DatasetManifest.purpose`, `window_days`, `universe`, `taxonomy`, `cohorts`, the `split` fields of 7.7, `Dataset.purpose` and `Dataset.cohorts`, the deletion of `Dataset.is_demo_pack`, `BuildConfig.purpose`, `universe_min_settled`, `universe_min_volume_cents`, `NEWS_SOURCES` gaining `hn`, `NEWS_KINDS` gaining `story`, `RejectReason.bad_rule`, `Actions.propose_rule` | `src/pmx/types.py` (D1) | DS1 for the data names in lot 5b, A1 for the agent and observation names in lot 6, the first engine lot for `Observation.sensors` and `RunConfig.sensor_catalogue_hash` (below), each as gate G2 applied 17.9's row |
| R232, R236, R248, R263, R266: `SensorAbsentError`, `RuleRefusedError`, `FoldIntegrityError`, `ShowcaseDatasetError`, `CohortRefusedError` | `src/pmx/errors.py` (D1) | S1, S2, DS1, DS1, DS2 respectively, each adding its own class in lot 5b by the agreement of section 13 |
| R231, R243, R265, R274: `observation_built.sensors`, `run_started.sensor_catalogue_hash`, `market_listed`'s `provider_labels`, `subject`, `structure`, `horizon`, the `rule_proposed` and `workflow_step_executed` dataclasses, `hive_written.kind = "insight"`, `action_rejected.scope = "rule"`; `journal.v2.json` promotes the fields to `required` and admits the two events to `oneOf` in the same commit | `pmx.journal` (D7); the `required` lists, `oneOf` and the backtest fixture (C1c's files) | the first engine lot after this amendment, with R213, R214, R217 and R221 (15.10, ruling R274) |
| R238, R254: `family_registered`, `rule_tested`, `rule_promoted`, `rule_demoted`, `candidate_scored.tier`, `diet_cost_units`, `sensors`, `n_rules_proposed`, `generation_closed.sensor_budget_next`, `culled_by_budget`, `rule_rewards`, `children.op = "sensor_drop"` | `pmx.journal` (D7), `journal.v2.json`'s `oneOf` and `required` lists (C1c) | gate G4, in the commit that lands O2's evolution journal |
| R230, R233: `build_observation(..., sensors=genome.sensors)` in the runner; the `SensedBar` and `SensedHiveView` gates and the news source filter in the observation builder | `src/pmx/engine/runner.py` (E5), `src/pmx/engine/observation.py` (E1) | A1's lot (the runner reads `genome.sensors` once `Genome` carries it); S1 for the three nested gates, by the agreement of section 13 |
| R238: `benjamini_hochberg` | `src/pmx/metrics/stats.py` (E4) | S2, by the agreement of section 13 |
| R230, R236, R243: `SCHEMA_FILES` gaining `rule.v1.json`, `sensor.v1.json` and `workflow.v1.json` (the three files exist and validate; 7.13) | `src/pmx/data/schema.py` (D1) | DS1, lot 5b, as gate G2 applied 17.9's row |
| R253, R254, R255: the two-tier fitness, the generator statement's `note`, the capacity metric | `src/pmx/optimizer/evolution.py`, `archive.py` (O2), `claims.py` (O4), `src/pmx/metrics/capacity.py` (O4) | lot 6 |
| R251, R260, R262: the hourly headline build, the cohort target and the fallback order as build outcomes, `window_days` and `purpose` in every manifest | `src/pmx/data/builder.py`, `cli_data.py` (DS1) | lot 5b |
| R247, R248: `make_folds` reads the manifest's count-quantile cuts and cluster moves; `open_sealed_test` unchanged in form | `src/pmx/optimizer/folds.py` (O1) | lot 6 |
| R252: the `contamination_audit: "coarse"` label and the live-replication guard on an LLM claim | `src/pmx/llm/contamination.py` (A6), `claims.py` (O4) | lot 6 |
| R261, R269, R273: the API serves the research dataset by default, the paged and filtered market index, the cohort view, the rule ledger routes | `src/pmx/api/*` (U1), `web/src/**` (U2, U3) | lots 5b and 7 |
| R274: the pinned config hash of `tests/test_runner.py`, `tests/test_types_loader.py`'s `is_demo_pack` uses, and every test that spells a name this amendment renames | the owning package's test file | the lot that applies the rename; a test that disagrees with the contract is the one that is wrong |
| R281, R285, R287, R298, R299: `RULE_PROPOSAL_COST_UNITS`, `SENSOR_BUDGET_UNITS_DEFAULT = 18`, `RunConfig.sensor_budget_units` and `sensor_budget_by_agent`, `SensorFeatureSpec.sentinel`, the derived `granularity_ms` and `lag_ms`, `BuildConfig.instruments`, `RULE_PERMUTATIONS_MIN`, `RULE_PERMUTATIONS_MAX`, `RULE_PROPOSALS_PER_GENERATION_MAX`, `ARCHIVE_CELLS_REACHABLE`, `SENSOR_SETS_UNDER_TEST`, `torch_policy.required_sensors` | `src/pmx/types.py` (D1), `src/pmx/sensors/catalogue.py` (S1), `src/pmx/agents/registry.py` (A1) | DS1 for `BuildConfig.instruments` in lot 5b, S1 for the catalogue names, A1 and O2 for the budget and archive names in lot 6, each as gate G2 applied 17.9's row |
| R278: `SensorInputs`, `run_workflow`'s signature and `StepTrace` as 12.11 declares them | `src/pmx/types.py` (D1) for `SensorInputs` and `StepTrace`, `src/pmx/agents/workflow.py` (A1) for `run_workflow` | S1 and E1 fill `SensorInputs` in lot 5b and lot 6; A1 returns the `StepTrace` tuple and E5 journals it in lot 6 |
| R279, R280: `Rule.readable_by`, the diet-narrowed `blocks` the runner hands the hive, `InsightView.required_sensors`, the `claim.direction` and `claim.kind` filter of the `rules` step and of `rule_follower` | `src/pmx/rules/rule.py` (S2), `src/pmx/agents/hive.py` (A3), `src/pmx/agents/families/rule_follower.py` and `workflow.py` (A1), `src/pmx/engine/runner.py` (E5) | S2 in lot 5b, A1, A3 and E5 in lot 6 |
| R282: `rule_permutation_p_ppm` beside `benjamini_hochberg` | `src/pmx/metrics/stats.py` (E4) | S2, by the agreement of section 13, in the same commit as `benjamini_hochberg` |
| R283, R288, R289: the deletion of `--cohort` and of `access.jsonl`'s `cohort_id`, `cohort_or_refuse`, `market_listed.cohort_id`, `diet_class` from `observation_built.sensors` | `src/pmx/optimizer/claims.py` (O4), `src/pmx/cohorts.py` (DS2), `pmx.journal` (D7), `src/pmx/metrics/projection.py` (E5) | DS2 in lot 5b, O4 and E5 in lot 6, the `market_listed` field with R274's lot |
| R277, R290: `fold_key_ms` as the cut key, `split.realised_permille`, the empty-fold and empty-rolling refusals, the clipped `Folds.rolling`, `build.status` per venue | `src/pmx/data/builder.py` and `loader.py` (DS1), `src/pmx/optimizer/folds.py` (O1) | DS1 in lot 5b, O1 in lot 6 |
| R291: `ShowcaseDatasetError` and `LeakError` on a carry-forward from a showcase or a foreign dataset | `src/pmx/engine/runner.py` (E5) | the first engine lot after this amendment, with R274's shapes |
| R292: the three-state capacity formula | `src/pmx/metrics/capacity.py` (O4) | lot 6 |
| R296: the `audits/<dataset_hash[:16]>/` tree (`.gitignore` needs no change: it never names `audits/`, so the tree is tracked by default) | `src/pmx/data/builder.py`, `cli_data.py` (DS1), `src/pmx/data/taxonomy.py` (DS2) | lot 5b; gate G3 fills the verdicts |
| R294: widening `test_rule_8_analysis_writes_no_journal_and_reads_no_sealed_fold` is **not** wanted; the test keeps scanning `analysis/` alone | `tests/test_architecture.py` (C1c) | nothing to apply: the text now says what the test does |
