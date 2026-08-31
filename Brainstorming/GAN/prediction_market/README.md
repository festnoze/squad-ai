# pmx: a prediction-market backtest arena

Replay **real resolved prediction markets** tick by tick, let a roster of agents forecast and trade
against the actual price evolution, and score them the only honest way: by **Brier** (how good their
stated probability was) and by **PnL** (what their trades made after costs) once the market resolves.
Reality is the referee. No metric depends on an LLM judge.

This is idea #1 from `GAN/docs/REAL_WORLD_ARENAS.md`, built on paper money, with a clean path to a live
account: the same loop runs on genuine imported data or on a small real position with no redesign.

## What it answers

Across a set of real markets, which agent (or skill, or prompt) forecasts best, which actually **beats
the market**, and does that edge **survive out of sample**. Beating the market is meant to be hard; the
walk-forward split is there to stop a lucky past from masquerading as a real strategy.

## The data, honestly

The bundled dataset is 12 **real resolved events with real, verifiable outcomes** (Brexit, Trump 2016
and 2024, the 2022 Ethereum Merge, BTC to 100k in 2022, the 2023 US recession that never came, LK-99,
and more). The **outcomes are real**; the **price paths are reconstructed**, a plausible trajectory
consistent with how each market actually behaved. Every bundled market is flagged `source:
"reconstructed"` and the UI shows the badge, so a reconstructed path is never mistaken for a real tape.

For genuine tapes, `pmx import <polymarket-slug>` pulls a resolved market's real price history from
Polymarket (needs a network) and writes it with `source: "imported"`. The engine and UI treat both
identically.

The mix is deliberate: some markets the crowd got right, some upsets where the price was wrong until
late, and some bubbles that collapsed. That spread is what gives agent selection real signal.

## The agents

Eight scripted forecaster-traders, each a pure function of the observation. Belief and trade are one
decision: an agent takes a position exactly to the extent it disagrees with the price, so its PnL is
positive only when its disagreement was right, after the spread it paid.

| agent | idea |
|---|---|
| `market_follower` | believe the price exactly. The baseline every agent is measured against. |
| `calibrated` | shrink the price toward a coin flip (a favorite-longshot correction). |
| `sharp` | believe the price but lean into a confirmed trend. |
| `momentum` | extrapolate the recent move. |
| `mean_revert` | fade extremes toward a coin flip. |
| `contrarian` | bet against the crowd outright (usually wrong, on purpose). |
| `anchor` | fix on the first price seen and never move. |
| `stubborn` | a coin flip forever. |

## Install

```powershell
py -3.12 -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[dev]"
```

## Run (backend)

```powershell
# write the bundled markets to data/markets/
.venv/Scripts/python.exe -m pmx.cli data seed

# score every agent on one market
.venv/Scripts/python.exe -m pmx.cli backtest data/markets/brexit-2016.json

# rank agents across all markets
.venv/Scripts/python.exe -m pmx.cli tournament

# pick the best on the past, grade it on the held-out future
.venv/Scripts/python.exe -m pmx.cli walkforward

# import a real Polymarket market (needs network)
.venv/Scripts/python.exe -m pmx.cli import will-trump-win-the-2024-election

# serve the API (read-only) on port 8175
.venv/Scripts/python.exe -m pmx.cli api serve --port 8175 --data data/markets
```

Everything that scores is free, deterministic, and byte-for-byte reproducible: a run is a pure function
of `(market, agents, spread)`.

## Run (web UI)

```powershell
# terminal 1: the API
.venv/Scripts/python.exe -m pmx.cli api serve --port 8175 --data data/markets

# terminal 2: the dashboard (proxies to the API on 8175)
cd web
npm install
npm run dev            # http://localhost:5510
```

Or just double-click `run.bat`, which starts both and opens the browser. If 8175 is busy, `run.bat 8176`
uses another port and the UI follows.

The UI has three views: **Market replay** (watch the price evolve with each agent's forecast tracking
it, the outcome hidden until the end, then revealed as a green YES or red NO line), **Leaderboard**
(who beats the market across all markets, with a skill bar), and **Walk-forward** (train on the past,
grade on the future, with an overfit verdict).

## The scoring, precisely

Money and prices are integers. A YES contract is priced in whole cents in `[1, 99]` and settles at 100
(YES) or 0 (NO). A stated probability is parts-per-million. Brier is computed in micro-units, no float.
The headline forecasting score is Brier **averaged over the market's whole life**, compared to the
market's own life-average Brier over the same ticks; scoring only the final belief would be trivial,
because the closing price has already converged on the outcome.

## Layout

```
src/pmx/
  types.py            Market, PricePoint, Observation, Action, AgentResult
  scoring.py          Brier and price/probability conversions, integers only
  agents.py           the eight scripted forecaster-traders
  engine.py           the deterministic backtest: replay one market, score everyone
  metrics.py          the leaderboard aggregation
  tournament.py       run all agents over all markets, plus the walk-forward split
  data/loader.py      load and validate market JSON
  data/bundled.py     the 12 real resolved events (reconstructed paths)
  data/importer.py    pull genuine tapes from Polymarket (needs network)
  api/                FastAPI, read-only
  cli.py              pmx data seed | backtest | tournament | walkforward | import | api serve
web/                  React 19 + Vite + TypeScript on port 5510
```

## Honest caveats

Real markets are near-efficient, so a positive result is the hard case, and proving an apparent edge is
noise (the walk-forward often does exactly that) is a valid, valuable outcome. The bundled reconstructed
paths are for demonstrating the machinery; quantitative claims should be made on imported real tapes,
on a sealed test set, after fees.
