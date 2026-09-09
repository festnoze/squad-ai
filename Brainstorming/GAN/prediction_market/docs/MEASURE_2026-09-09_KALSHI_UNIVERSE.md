# Measurement of 2026-09-09 : the reachable Kalshi universe, before lot 5b builds anything

Decision **D-S12** of `docs/REVIEW_2026-09-09_SCALE_TAGS.md` says package DS1 must report the reachable
count against the cohort target **before** building, and it fixes the fallback order in advance. This
file is that report, taken from this machine against the live public API, so that lot 5b starts from a
measurement instead of a hope. It answers one question: is the target of decision D-S11 (40 usable
cohorts on Kalshi, which decision D-S12 puts at about 7 000 markets) reachable at all?

Probes: `scratchpad/kalshi_universe_probe.py` and `scratchpad/kalshi_series_probe.py`, one request at a
time, a throttle between pages, a hard page cap, and the descriptive user agent with a contact the
project requires. No authentication was used or needed.

## 1. The market count is not the constraint

| Quantity | Value |
|---|---|
| pages fetched (1 000 markets each, `status=settled`, newest first) | 60, **the cap, so there are more** |
| markets seen | **60 000** |
| of those, settled inside 365 days of the 2026-09-07 freeze | **60 000** |
| settled more than 730 days before the freeze | 0 |

The raw settled universe inside the one-year window is at least sixty thousand markets and the probe
stopped on its own cap, not on the data. So the ~7 000 markets that 40 usable cohorts imply are not a
scarcity problem.

## 2. The walk order is the constraint

| Quantity | Value |
|---|---|
| median market life in the 60 000 | **0.04 days**, about one hour |
| markets living at least 7 days | **0 of 60 000** |
| distinct event tickers | 49 756 |
| event tickers with at least 30 markets | 20 |

The newest-first settled listing is saturated by the auto-generated short-lived markets the contract
already calls Kalshi shards (`BuildConfig.exclude_kalshi_shards`, and the `min_life_days` filter). Not
one of sixty thousand would survive the life filter. **A market-level walk therefore cannot find the
tradable universe at any budget**, which is the real reason the earlier build spent its 400-row budget
on 252 one-day markets and why a series list was hand-picked. Raising the per-provider cap alone, as
decision D-R7 lifted it, does nothing on its own.

## 3. There is a public series endpoint, so the universe rule can be built at the right level

| Probe | Result |
|---|---|
| `GET /trade-api/v2/series` | **HTTP 200, 13 917 series**, no authentication |
| `GET /trade-api/v2/series?limit=5` | same payload, the limit is ignored |
| `GET /trade-api/v2/events?status=settled` | HTTP 200, paginated, carries `category` per event |
| `GET /trade-api/v2/series/list` | HTTP 404, does not exist |

This is what makes decision **D-S13** buildable as written: the series list becomes an **output** of the
builder rather than a hand-picked input. The rule can be stated over the 13 917 series (a minimum count
of settled markets in the window and a minimum volume, both counted from the series' own markets), and
the market walk then runs **per series** instead of newest-first over the whole exchange.

## 4. Two corrections to what a naive probe assumes

1. **The listing field names are the newer ones.** A settled market row today carries `volume_fp`,
   `volume_24h_fp`, `open_interest_fp`, `liquidity_dollars`, `last_price_dollars`, `yes_bid_dollars`,
   `yes_ask_dollars` and `settlement_value_dollars`. The old integer-cent spellings (`volume`,
   `yes_bid`, `last_price`) are **absent**. This is **not** a defect in the project: the importer
   already reads both spellings through its `_either` helper and documents the rename at
   `src/pmx/data/importers/kalshi.py` lines 287 and 288. The measurement is recorded here as a
   **confirmation that the importer matches the live API on 2026-09-09**, which is worth having written
   down, because a silent rename is exactly the kind of upstream change that would otherwise turn every
   volume into a zero.
2. **`data/datasets/y2026/kalshi_series.txt` is one single comma-separated line**, not one ticker per
   line. A per-series probe that reads it line by line passes the whole file as one ticker and gets
   zero markets back, which is what happened on the first attempt here. DS1 should either normalise the
   file to one ticker per line when it becomes a build output, or the readers must split on commas.

## 5. What this means for lot 5b

* The cohort target of decision D-S11 is **reachable**, and the fallback order of D-S12 is **not needed
  for scarcity**. It stays as written for the case where the filters, not the universe, bind.
* Package **DS1's universe rule must be series-driven**, and that is now known to be possible without
  credentials. A market-level walk is the wrong shape and no budget fixes it.
* The number to report per build is therefore not "markets seen" but **how many series pass the rule and
  how many markets each contributes after each filter**, which is what decision D-S13 already asks the
  manifest to carry.
* The importer's field handling is current as of this date. Any future build that suddenly reports zero
  volumes should re-run these probes first.
