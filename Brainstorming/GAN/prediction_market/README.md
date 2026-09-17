# pmx: local prediction-market research workbench

Explore real historical markets, discover rules, optimize strategy parameters, and inspect their
forecasts and simulated trades. The French web interface uses the v2 engine and persisted journals.
This MVP is for a first user test and research feedback; it does not certify profitable trading.

The active roadmap is [PLAN_DISCOVERY_MVP](docs/PLAN_DISCOVERY_MVP.md), with scoped decisions in
[CONTRACTS_MVP](docs/CONTRACTS_MVP.md) and evidence in [DISCOVERY_MVP_STATUS](docs/DISCOVERY_MVP_STATUS.md).
The older waves and the September 13 starting snapshot are retained as historical references.

## Start on this machine

From this directory, run `run.bat` and open **http://127.0.0.1:8175**. It prepares or verifies the
local dataset, builds the interface and serves both UI and API in one process. Keep its terminal open;
Ctrl+C stops it. `run.bat 8176` selects another port. No network data import happens during startup.

After a successful build, the shorter restart command is:

```powershell
.venv/Scripts/python.exe -m pmx.cli mvp serve --port 8175
```

Prerequisites for a fresh checkout are Python 3.12+, Node.js with npm, and the local historical snapshot
at `data/datasets/y2026`. Dataset files and generated runs are ignored by Git. The snapshot is already
present on this machine; a new checkout needs a separate copy. Missing source data raises an explicit
error; the application does not substitute reconstructed demonstration data.

```powershell
py -3.12 -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[dev]"
cd web
npm.cmd ci
cd ..
.\run.bat
```

## First test

New users can follow **Comprendre avant de lancer**, the five-step tutorial shown on first visit and
reopenable above the dataset selector. A written version is in [GUIDE_DEBUTANT](docs/GUIDE_DEBUTANT.md).
Recorded experiments and campaign finalists now have interactive return, capital and drawdown charts,
with agent visibility controls and a date slider. Campaign curves share a validation period and universe.

The **Signaux** screen runs the fixed R1 protocol on `polyarchive2024h1`, with calibration plots,
monthly effects, missing-target coverage, descriptive screening and JSON observation exports.
Read [R1_SIGNAL_PROTOCOL](docs/R1_SIGNAL_PROTOCOL.md) before interpreting the 28 variants. This is a
training-only descriptive study; it does not optimize a strategy or establish a certified edge.

The completed R1 study, its measured results and reproducibility hashes are recorded in
[R1_RESULTS_2026-09-14](docs/R1_RESULTS_2026-09-14.md). To prepare the same new cohort from the pinned
archive (the 2023 corpus remains the historical protection reference):

```powershell
.venv/Scripts/python.exe -m pmx.cli archive download --start-date 2024-01-01 --end-date 2024-07-01 --skip-ctf
.venv/Scripts/python.exe -m pmx.cli archive project-ctf --end-date 2024-07-01 --cutoff-block 60000000
.venv/Scripts/python.exe -m pmx.cli archive build --output-dir data/datasets/polyarchive2024h1 --start-date 2024-01-01 --end-date 2024-07-01 --max-markets 1500 --ctf-projection-dir data/external/polymarket-v1/.projections/ctf-before-60000000
```

Restart the app after preparing a new cohort, select it, and open Signaux. The completed study on this
machine is already available; these acquisition commands are not required to inspect it.

Use **Decouvrir** to run a bounded campaign (12, 30 or 60 trials). It mines short conjunctions from
completed observations and searches level, momentum and reversal parameters with Optuna. Each candidate
uses independent capital and liquidity, internal training periods and later validation of frozen
finalists. Inspect rejected trials, executed rules, results per period, the no-trade reference and the
finalist replay. Cancellation takes effect between evaluations. A finalist need not be profitable.
The latest delivered `polyarchive2024h1` dataset is selected by default on a fresh browser. Initial archive
verification can take several minutes; the server caches the verified corpus until restart.

Use Signaux for the current R1 result. The command below reproduces the earlier 2023 discovery pilot;
it is not a new independent evaluation or the recommended next optimization campaign.

```powershell
.venv/Scripts/python.exe -m pmx.cli mvp search --dataset polyarchive2023 --provider polymarket --n-trials 12
```

After a campaign, **Ce que les résultats nous apprennent** displays a French Codex review with
evidence, limitations and suggested next tests. Enable the checkbox to trigger one review for each
new completed result, using the local Codex CLI signed in with ChatGPT (`codex login status`). This
consumes the subscription quota; API-key authentication is refused. The setting is off in a fresh
checkout and enabled on this machine. Old campaigns require the explicit analysis button; saved
reviews are reused, and failures require a manual retry. Reports and evidence are downloadable and
persist under `runs/mvp/analyses/`. Keep one application/CLI owner per runs directory.

The first Polymarket campaign showed no demonstrated edge. Read the measured diagnosis and proposed
signal-first next steps in [POST_CAMPAIGN_REVIEW_2026-09-13](docs/POST_CAMPAIGN_REVIEW_2026-09-13.md).

The original fixed-strategy comparison remains available:

1. In **Explorer**, inspect the dataset, filter by provider or category, and open a market to see its
   price, volume and timestamped news. The legacy grid is daily; archive datasets are hourly.
2. In **Experiences**, choose Kalshi, validation, the three strategies, seed 7 and 12 markets. Launch
   the experiment and wait for its persisted result.
3. Compare Brier and forecast skill separately from net simulated PnL, fees and drawdown. Open a market
   replay to inspect probability curves, positions and actual fills.
4. Reload the page and reopen the experiment from history. Export the JSON result for feedback.

`follower` tracks the observable market probability and never trades; it is the control. `trend`
extrapolates recent price movement. `revert` moves the estimate toward the recent mean. Their fixed parameters are
visible in the interface. These strategies neither learn nor use a language model.

CLI access runs the same engine and writes into the same experiment history:

```powershell
.venv/Scripts/python.exe -m pmx.cli mvp run --provider kalshi --fold validation --seed 7 --max-markets 12
```

## Data and interpretation

The public Polymarket archive importer is optional and independent of application startup:

```powershell
.venv/Scripts/python.exe -m pip install -e ".[dev,archive]"
.venv/Scripts/python.exe -m pmx.cli archive inventory
.venv/Scripts/python.exe -m pmx.cli archive download --start-date 2023-01-01 --end-date 2024-01-01 --skip-ctf
.venv/Scripts/python.exe -m pmx.cli archive project-ctf --end-date 2024-01-01 --cutoff-block 60000000
.venv/Scripts/python.exe -m pmx.cli archive build --output-dir data/datasets/polyarchive2023 --start-date 2023-01-01 --end-date 2024-01-01 --max-markets 1500 --ctf-projection-dir data/external/polymarket-v1/.projections/ctf-before-60000000
.venv/Scripts/python.exe -m pmx.cli mvp search --dataset polyarchive2023 --provider polymarket --n-trials 12
```

Pinned source: `TimeSeventeen/Polymarket-v1@5aa1b9d52316a8b2e789e81c8ae42c7ed532e8aa` (CC BY 4.0).
Full selected inventory is 13.37 GB; the recipe above downloads a complete 2023 slice and a proven
CTF projection using much less bandwidth. It checks every event ID against a verified cutoff block,
retains exact HTTP ranges and hashes, and explicitly reports partial-object verification. Whole-file
LFS checksums are verified only for full objects. Omit the date flags and `--skip-ctf` to resume the full
archive instead. Default transport is verified HTTPS; Xet is opt-in. Build requires every
partition for its requested date range and the CTF metadata. Progress and resume information live
under `data/external/polymarket-v1/download-manifest.json`. A partial download is not a complete corpus.
The archive uses native USDC, retains censored cases beside the settled adapter and hides inferred
expiry from strategies. Historical books and fee schedules are absent: the 20 bp execution fee is an
explicit scenario, not an upper cost bound. Existing OHLC limits can clip simulated spread.

The delivered 2023 corpus identifies 2,423 traded conditions and selects 1,500 by an outcome-blind hash.
Its adapter contains 1,273 eligible settled markets and 365,980 hourly bars, of which 29,644 contain
observed trades. The remaining bars carry the previous price with zero volume. There are 763 training,
255 validation and 255 sealed markets; 1,018 are available in the UI. Selected censored or ineligible
conditions remain documented beside the adapter. Required downloaded sources total 39,662,850 bytes;
the complete 13.37 GB archive remains resumable and paused. See the measured status for its hash and
campaign evidence. Neither all blockchain activity nor independent event groups are reconstructed.

The MVP derives `data/datasets/mvp2026` from all 287 markets in the existing `y2026` snapshot without
altering that source. The builder assigns chronological folds again and the loader verifies the new
manifest and hashes. Of these markets, 172 are training, 53 validation and 62 sealed. Sealed markets
are excluded from both the browser and the run API. Provider currencies remain separate: Kalshi uses
USD and Manifold uses virtual currency. The maximum experiment size is 30 markets.

Validation is exploratory once inspected repeatedly. Coverage shortfalls, sparse or synthetic source
components, and execution approximations are disclosed with the dataset and results. An experiment
uses shared simulated liquidity across its roster, so changing the roster can change execution.
Runs include population, genomes and engine version in their identity and keep deterministic journals.
The API shows equal-weight market-average Brier scores and their market baseline; positive forecast
skill does not imply positive trading PnL. No confidence interval or robustness certification is shown.

Result files are under `runs/mvp`; each completed run contains its journal and JSON views. Job state is
persisted too. One experiment runs at a time; another request while busy receives HTTP 409. Restarting
the server marks unfinished jobs as failed and preserves completed results. Bind address is loopback;
this MVP is a single-user local application, without authentication or multi-process coordination.

## Develop and verify

For web development, keep the API running on 8175, then run `npm.cmd run dev` inside `web`. Vite proxies
`/api` to the backend. Set `PMX_API` before starting Vite to use another API port.

```powershell
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m ruff check src tests
.venv/Scripts/python.exe -m mypy src
cd web
npm.cmd run build
```

Main code: `data/prepare_mvp.py` prepares the snapshot; `agents/registry.py` defines the fixed roster;
`api/` exposes datasets, background jobs and persisted results; `engine/` runs the deterministic
calendar; `web/src/` provides the interface. The legacy CLI commands and `pmx.v1` remain available for
historical fixtures, but `pmx mvp` and `run.bat` are the active application entry points.

Campaigns generate hypotheses. Their training totals sum independent simulations; open inventory is
marked at period ends rather than force-liquidated. Repeatedly inspected validation becomes development
data. No statistical certification or execution-cost stress result is implied. Future learned models
can share this evaluation path; RL, LLMs and multi-asset expansion require evidence of added value.
