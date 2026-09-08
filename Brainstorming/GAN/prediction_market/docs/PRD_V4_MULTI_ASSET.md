# PRD v4 : pmx across every market (prediction, crypto, FX, equities, futures)

Extension of `docs/PRD_V2_HARD_OPTIMIZER.md` and `docs/PRD_V3_TRADING_OPTIMIZER.md`. Until now the
arena was built for prediction markets: binary contracts that resolve to a truth. v4 widens it to any
traded market (crypto spot and perpetuals, foreign exchange, equities and ETFs, futures) while keeping
every principle that made the prediction-market version honest: integers only, a journal that replays,
as-of information, real fees and liquidity, sealed held-out claims with intervals, and reality as the
only referee. The prediction-market contract becomes one **instrument kind** among six.

Written 2026-09-08 after probing every data source below from this machine. `docs/CONTRACTS_V2.md`
remains the technical source of truth; the instrument generalisation enters it through amendment C1b
before the engine wave starts (`docs/PLAN_V3_WAVES.md`).

---

## 0. Why now, and what does not change

- The engine wave (E1..E5) has not started. Generalising the instrument model today costs one contract
  amendment; doing it after the engine exists would cost a rewrite of execution, scoring and the runner.
- Everything of v2 and v3 stays: the data seal, the calendar of bars, the latency rule, the liquidity
  protocol and its envelope, the agent protocol, memory and hive, evolution, detectors, learned agents,
  the adversarial market maker, the claims ledger, the end-to-end ladder.
- The referee changes shape but not nature. A binary contract is judged by its resolution. A continuous
  instrument is judged by its **realised price path**: a forecast made at `t` for horizon `h` is scored
  against the price at `t + h`, and a position is scored by the money it made after costs. Both are
  facts about the world, logged before they are known.

---

## 1. The instrument model

### 1.1 Kinds

| Kind | Examples | Terminal settlement | Short side | Carry |
|---|---|---|---|---|
| `binary` | Kalshi, Manifold, Polymarket contracts | yes, at resolution, to 10000 or 0 bp | buy NO at `10000 - price` | none |
| `spot_crypto` | BTCUSDT on Binance, XBTUSD on Kraken, BTC-USD on Coinbase | none; marked to market; forced flat at the window end | only via a `perp` twin or disallowed (config) | none |
| `perp` | BTCUSDT linear perpetual on Binance or Bybit | none; funding every 8 hours | native | funding rate, signed, per funding time |
| `fx` | EURUSD, USDJPY | none | native (selling the base) | overnight swap, approximated by the rate differential (config, off by default) |
| `equity` | AAPL, SPY | none; corporate actions adjust the series | allowed with a borrow fee schedule (config) | dividends as cash events on the ex-date when the raw series is used |
| `future` | ES, CL, GC, ZN, 6E continuous contracts | expiry per contract; the continuous series rolls by a declared rule | native | none; the roll gap is recorded, never traded through |

### 1.2 Prices as integers, for every kind

Every instrument declares `tick_size_micro` (the smallest price increment, in millionths of one quote
unit) and `point_value_micro` (the cash value of a one-point move of one unit of position, in millionths
of the quote currency). Prices are stored as `price_ticks: int`. Cash is integer cents (or the quote
currency's minor unit). Position value and PnL are exact integer arithmetic on those three integers.

- A binary contract is `tick_size_micro = 10_000` (one basis point of a one-unit payout),
  `point_value_micro = 1_000_000` on a one-dollar payout: `price_ticks` is the bp price v2 already uses.
  Nothing written for prediction markets changes value.
- BTCUSDT on Binance is quoted to the cent: `tick_size_micro = 10_000`; one unit is one coin, so
  `point_value_micro = 1_000_000`. A position of `size_milli = 1` is one thousandth of a coin.
- ES is quoted in quarter points with a fifty-dollar multiplier: `tick_size_micro = 250_000`,
  `point_value_micro = 50_000_000`.
- EURUSD is quoted to the pip (a tenth of a pip on some venues): `tick_size_micro = 100` or `10`.

The conversion formulas, the rounding rule (round half up, once, at the end) and the overflow bounds
(all products fit in 63 bits at the declared scales) are contract material for C1b.

### 1.3 Sessions and calendars

Bars exist only inside an instrument's **session calendar**: crypto is continuous; FX is continuous from
Sunday 22:00 UTC to Friday 22:00 UTC; equities and futures follow their exchange's regular hours and
holidays (a static calendar file per exchange, sealed with the dataset; extended hours excluded by
default). The run calendar of v2 is the union of the instruments' bar timestamps; an instrument with no
bar at `t` is simply not tradable at `t` (the same rule a closed prediction market obeys).

### 1.4 Corporate actions, rolls, funding

- Equities are stored **raw**, with the split and dividend history as dated `CorporateAction` records; the
  loader offers an adjusted view for features and charts, while execution and PnL run on raw prices
  plus cash events, so a dividend is money on the ex-date and a split is a position multiplication.
- A future's continuous series records every roll as a dated `Roll` with the gap; a position held across
  a roll is closed on the expiring contract and reopened on the next at their respective prices, paying
  two fills. Yahoo's continuous contract is a convenience source and is flagged as such; a dataset built
  from it is labelled `roll_source: "vendor"`.
- Perpetual funding is a dated cash flow applied to open positions at each funding time, from the
  venue's published history (Binance and Bybit expose it).

---

## 2. Data sources (verified 2026-09-08 from this machine)

| Source | Status | Data | Role |
|---|---|---|---|
| **Binance** spot `api.binance.com/api/v3` | 200: `klines` (1m to 1M, 1 000 per call), `aggTrades` | Deep OHLCV and trade prints for the top crypto pairs | Primary crypto tape |
| **Binance** futures `fapi.binance.com/fapi/v1` | 200: `fundingRate` history | Perpetual funding | Carry for `perp` |
| **Kraken** `api.kraken.com/0/public` | 200: `OHLC` (up to 720 bars per call), `Trades` (paginated by `since`) | Second crypto venue, plus fiat pairs | Cross-venue crypto clusters, FX cross-check |
| **Coinbase** `api.exchange.coinbase.com` | 200: `candles` (300 per call) | Third crypto venue | Cross-venue clusters |
| **Bybit** `api.bybit.com/v5/market/kline` | 200: linear klines | Perpetual second venue | Perp clusters, funding divergence |
| **Yahoo chart v8** `query1.finance.yahoo.com/v8/finance/chart/<symbol>` | 200 for `AAPL`, `ES=F`; hourly bars for about two years, daily for decades, `EURUSD=X` for FX | Equities, ETFs, continuous futures, FX | Primary equities and futures tape; **unofficial and rate-limited**, so cached, throttled, and labelled `vendor: "yahoo"` in every manifest |
| **Frankfurter** `api.frankfurter.app` and **ECB** `data-api.ecb.europa.eu` | 200 | Daily FX reference rates | Official daily FX anchor; the truth for daily FX claims |
| **SEC EDGAR** `data.sec.gov/submissions/CIK<10 digits>.json` | 200 with a descriptive User-Agent (the full-text search endpoint returned 403 and is not used) | Every filing of a company with acceptance date and time | **Dated company news** for equities, as-of by acceptance time |
| **FRED** `fred.stlouisfed.org/graph/fredgraph.csv?id=` | 200 | Macro series | Macro context; **as-of requires ALFRED vintages** (`alfred.stlouisfed.org`), because FRED revises history; a series without a vintage is features-only with a declared lag |
| **CBOE** `cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv` | 200 | VIX daily history | Volatility regime feature |
| Stooq | JavaScript challenge page, no data | | Not used |
| Dukascopy tick feed | connection reset | | Not used |

Every financial instrument records `provider`, `vendor`, `symbol`, `kind`, `currency`, the tick and point
scales, the session calendar id, the fee and carry schedule ids, and `source: "imported"`. The
twelve-month window, the freeze date, the seal, the as-of rule and the split into folds are the same as
for prediction markets, so that cross-domain clusters (section 4) line up in time.

### 2.1 Fees and costs as data

Per venue and kind, with a source URL and a date: Binance spot and futures taker fees, Kraken and
Coinbase tiers, an equity commission model (zero commission plus a half-spread estimate and an SEC fee
on sales), a futures round-turn commission plus exchange fee, an FX spread model per pair and session.
When no quote is available the half-spread is estimated from the bar (the Corwin and Schultz estimator
on high and low, per contract formula), and the envelope rule uses that estimate as the floor.

### 2.2 Universe for the first multi-asset dataset

Over the same twelve-month window as `y2026`: the top 20 crypto pairs by volume on Binance with their
Kraken and Coinbase twins and their Binance and Bybit perpetuals; the seven FX majors; the fifty largest
US equities plus eleven sector ETFs and SPY, QQQ, TLT, GLD; six continuous futures (ES, NQ, CL, GC, ZN,
6E). Hourly bars are the primary grid for finance (crypto has about 8 700 per pair per year), daily as
a second dataset. Universe statistics are part of the manifest as in v3.

---

## 3. Scoring across kinds

Trading metrics are universal and unchanged: PnL after all costs (fees, funding, borrow, roll fills),
return on bankroll, drawdown, a Sharpe-like ratio on bar-by-bar equity, turnover, fill ratio, ruin,
exposure by kind and by instrument, the robustness gap of v3.

Forecast metrics depend on the kind:

- `binary`: Brier, horizon Brier, skill versus the market price, log score, calibration, as in v2.
- Continuous kinds: an agent states, for each declared horizon `h` (config, default one bar, one day,
  one week), the probability that the return over `h` is positive, and optionally a set of return
  quantiles. The **directional Brier** at `t + h` against the realised sign, the **pinball loss** of the
  quantiles, and calibration curves per horizon are the forecast scores. The **baseline** every agent is
  measured against is the random walk: up-probability 500 000 ppm and the current price as every
  quantile, which is the efficient-market statement for a price series. Skill is baseline loss minus
  agent loss, in integer micro-units, with the bootstrap and permutation machinery of v2 (blocks by
  week; the permutation shuffles realised returns across instruments within a week).
- Every forecast "resolves" at its horizon with the realised price, so the hive, the calibration ledger
  and the reputation of v2 work unchanged: a `ForecastRecord` becomes visible one bar after its horizon.

The **beat-the-market bar** of v2 section 6.2 holds per asset class: a positive lower bound on
after-cost PnL and on forecast skill on the sealed test, deflated for the candidates compared, with the
permutation null at or below zero. For continuous instruments the honest expectation is that most
agents do not clear it, and that result is reported as such.

---

## 4. Cross-domain opportunities

A unified platform sees what a single-market tool cannot. New detector family for rung 2:

- **Binary versus underlying**: a Kalshi or Polymarket contract on "BTC above X on date D" against the
  Binance BTC path; the contract's price against a model-implied probability from the underlying's
  realised volatility, and the two paths' joint dynamics. The same for Fed-rate contracts against FRED
  and the rate futures, for election contracts against sector ETFs, for company-event contracts
  against the stock.
- **Funding and basis**: perpetual versus spot on the same coin (the basis), funding rate extremes,
  cross-venue perp divergence.
- **Cross-venue crypto**: Binance versus Kraken versus Coinbase on the same pair (spread net of fees and
  transfer time), the crypto analogue of v3's prediction-market divergence.
- **Macro releases**: price behaviour around scheduled releases (FOMC, CPI, payrolls) using the ALFRED
  vintage timestamps as the as-of clock, so that "the number" enters the world exactly when it did.
- **Filings**: post-filing drift after SEC acceptance times, the equity analogue of the news lead study.

Each detector emits `OpportunityEvent`s with the currency and the two providers, reports a lower bound,
an interval and a permutation null, and appears on the opportunity map of v3.

---

## 5. Agents across kinds

- Every scripted family of v2 runs unchanged where it makes sense (`trend`, `revert`, `breakout`,
  `volume`, `timedecay` on binaries only, `newsbayes` with finance lexicons). New families: `carry`
  (funding and rate differentials), `basis` (perp versus spot), `pairs` (cross-venue and cross-asset
  spreads inside a cluster), `vol_regime` (VIX and realised volatility gates), `calendar` (session and
  release effects).
- The `kelly` and `calibrator` overlays, memory, the hive and the stacker work on the generalised
  forecast records.
- The features of v3 gain the finance fields (returns at horizons, realised volatility, volume z-scores,
  funding, basis, session time, day of week, release proximity, cross-asset returns of the cluster).
  Crypto alone provides millions of hourly bars, which is where the GPU pipeline of v3 earns its place.
- The adversarial market maker generalises without change: the envelope now uses the estimated
  half-spread when no quote is known.

---

## 6. Surfaces

- The market view draws any kind on a true time axis (candles, volume, funding markers, roll markers,
  corporate action markers, SEC filing markers, release markers), with the outcome hidden until the
  cursor passes the horizon for continuous instruments and the resolution for binaries.
- The leaderboard and the claims ledger are per asset class and per provider; a claim names its kind.
- The CLI gains `pmx data import binance|kraken|coinbase|bybit|yahoo|frankfurter|edgar|fred|cboe`, and
  `pmx data build --kinds binary,spot_crypto,perp,fx,equity,future`.

---

## 7. Acceptance criteria added by v4

- AC-21: a multi-asset dataset builds from the network with at least the universe of section 2.2 at an
  hourly grid (or documents the shortfall), seals, verifies, and its clusters link at least ten binary
  contracts to their underlying instruments.
- AC-22: the accounting invariant holds for every kind under property tests, including funding, borrow,
  dividends, splits and rolls; a run on a mixed roster replays to an identical hash.
- AC-23: the random-walk baseline agent scores exactly zero skill on every continuous instrument, by
  construction, as `market_follower` does on binaries.
- AC-24: the cross-domain consistency detector finds a planted binary-versus-underlying mispricing on
  fixtures and nothing on the shuffled twin.
- AC-25: a claim on the sealed test is produced per asset class for the champion, whatever its sign.
- **E2E-1b** (`tests/e2e/test_e2e_1b_multi_asset.py`): a fixture with one crypto pair on two venues, its
  perpetual with funding, one FX pair, one equity with a split and a dividend, one future with a roll,
  and one binary contract on the crypto price builds, runs a mixed roster, journals every cash event,
  replays, and prints per-kind leaderboards.
- **E2E-2b** (`tests/e2e/test_e2e_2b_cross_domain.py`): the planted consistency mispricing and its null.

---

## 8. Risks specific to v4

| Risk | Mitigation |
|---|---|
| Yahoo is unofficial and can break or throttle | Cache everything, throttle, label `vendor: "yahoo"`, keep the official FX anchors (ECB) and the exchange APIs (Binance, Kraken, Coinbase) as the tapes that claims rest on; equities and futures claims carry the vendor caveat until an official source is added. |
| Survivorship in the equity universe | The universe is chosen by market capitalisation **at the window start** from a dated list, and the manifest says so. |
| Macro data revised after the fact | ALFRED vintages only for as-of features; plain FRED series are marked features-only with a declared lag and never enter a claim. |
| Continuous futures hide roll costs | Rolls are dated, gaps recorded, and every position pays two fills across a roll. |
| Extended-hours and holiday bars | Static session calendars sealed with the dataset; a bar outside the calendar is a load error. |
| Overfitting explodes with more instruments | The same discipline: folds, sealed test, deflation for candidates, permutation null, and the robustness gap. |
| Scope | The instrument model enters the contract now (C1b); importers and detectors for finance are their own wave and can slip without blocking the prediction-market ladder. |

---

## 9. Revision history

- 1.0, 2026-09-08: written after the user widened the scope to every market and after live probes of
  Binance, Kraken, Coinbase, Bybit, Yahoo, Frankfurter, ECB, SEC EDGAR, FRED, CBOE (working) and Stooq,
  Dukascopy (not usable from this machine).
