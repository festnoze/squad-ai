# MVP delivery status, 2026-09-13

## Active scope

This delivery starts from STATE_2026-09-13.md and follows PLAN_MVP.md and CONTRACTS_MVP.md.
The MVP is a complete local frontend/backend research workbench. Scientific certification, evolution,
LLMs, live orders, hive/memory and wider assets remain behind the first user-feedback checkpoint.

The implementation includes a verified derivative dataset, three real fixed strategies, filtered
market browsing, dated news, bounded background experiments, persisted history, results and journal
replay, JSON exports and a single-server Windows launcher. The web interface is French.

## Dataset evidence

- Source `data/datasets/y2026` is unchanged. The new `mvp2026` retains all 287 imported markets:
  220 Kalshi and 67 Manifold, with 9,049 news items.
- Corrected chronological folds: 172 training, 53 validation, 62 sealed. The 225 visible markets
  comprise 167 Kalshi and 58 Manifold; the browser and run API exclude sealed markets.
- Grid: daily, 1,440 minutes. Freeze date: September 7, 2026.
- Dataset hash: `201eb01fdcbd9485d07a1708bdb7b913d69b12d335b9a48aabdd0c8c03988eee`.
- Source hash: `83fbf21166899712e86ed7ac1cab13cfa9a9ce25201a9de6844ad4703209f554`.
- Preparation is offline, atomic and idempotent. Changed source/output bytes fail verification.
- Cohort coverage remains insufficient: the historical coverage build status stays `failed` and
  taxonomy audit stays null. Neither is reclassified as a scientific pass for this MVP.
- Automatic news links can be irrelevant. The UI discloses that limitation and shows only items
  available by the selected observation's end. The three MVP strategies do not consume news.

## Correctness changes and verification

The engine is version 2.1.0, contract amendment 2.1-mvp. Run identity now includes the canonically
ordered population, serialized genomes and engine version, in addition to dataset/configuration.
The v2 CLI hashes the actual Calendar market selection. Existing engine and accounting code is reused.

Live rule records now wait for target-bar completion or visible binary settlement. Regressions alter
only a future outcome and verify that the past record is unchanged, then verify that evidence becomes
available at the correct boundary. Rule trading remains deferred; this is not a claim that every
future statistical research path has undergone a new audit.

Critical mutation checks passed: removing population from run identity makes the collision regression
fail; making future targets immediately available makes both bias and drift regressions fail. The
unmodified four focused integrity/live-boundary tests pass. The architecture suite passes.

Global Ruff passes. Mypy passes over 100 source files. Production TypeScript/Vite build passes.
The full Python suite ran once: 1,437 passed, four live-network tests skipped, one obsolete assertion
failed because it expected the agent registry not to exist. That assertion now explicitly requests a
missing registry; it and a new bounded CLI test of the real registry pass (2/2). After adding HTTP
attachment exports, all 15 API tests pass again, including the real engine/replay/restart journey.
No failing check remains unresolved. The full suite was not repeated after those targeted fixes.

## First real browser experiment

The browser launched `r-201eb01f-7-adf29b31` on 12 Kalshi validation markets, seed 7, initial capital
USD 1,000 per agent. There are 50 equity timestamps and 251 actual nonzero simulated fills.

| Strategy | Mean Brier | Net simulated PnL (USD) | Fees (USD) | Fills |
|---|---:|---:|---:|---:|
| Market follower | 0.222257 | 0.00 | 0.00 | 0 |
| Mean reversion | 0.225564 | 5.37 | 12.17 | 121 |
| Trend | 0.228537 | -64.62 | 14.68 | 130 |

These are exploratory observations, not evidence of an economic edge. This small example already
illustrates why forecast quality and simulated money must remain separate in the interface.
Journal hash: `347332931b706f71dbb1bc87cb6427741581221b68a24ed64161d363f8aa5564`.
An independent CLI replay reconstructed the same results: three agents, 12 markets and 36 score rows;
the journal hash above was confirmed unchanged.

Browser checks passed for initial listing, an empty search, combined search/validation filter, run
launch and completion, result table, replay beginning/end and reopening the saved result after reload.
The production page was visually inspected. Empty query parameters initially caused 422 responses;
the frontend now omits them. Dataset counts now clearly refer to the explorable subset. News follows
the cursor and discloses unaudited automatic associations.

Exports use HTTP JSON attachment responses, verified against persisted detail/replay in integration
tests, with a live HTTP 200 plus Content-Disposition check and a browser download event after server
restart. This replaces temporary blob URLs.
The Windows launcher completed data verification, production build and server startup on port 8175.
A second browser-launched run on two Manifold validation markets completed with three strategies and
20 nonzero simulated fills. The interface displayed MANA, kept its history separate from Kalshi and
reopened the Kalshi result correctly. No provider currencies were aggregated.

## Runtime and limitations

Launch `run.bat`, then open http://127.0.0.1:8175. It verifies/prepares the local pack, builds the web
bundle and serves UI plus API on the same port. Restart an already-built app with
`.venv/Scripts/python.exe -m pmx.cli mvp serve`. Ctrl+C stops the foreground server.

First strict catalogue load measured 53.3 seconds during concurrent regression work. Subsequent tape
access uses the instance cache. The UI explains that initial verification can take one minute.
No cache bypasses hash verification when opening a new dataset instance.

Runs default to 12 markets and cap at 30, separated by provider/currency and fold. One background
worker accepts one active job; a second concurrent request receives a useful 409. Completed views
and journal artifacts live under `runs/mvp`. Interrupted jobs are marked failed on restart.
The API is a loopback, single-user service; multi-process coordination and remote deployment are
outside this MVP. Local datasets and generated experiment artifacts are not tracked by Git.

The market follower is the no-order control. Trend extrapolates four completed bars; reversion moves
toward the seven-bar mean. All fixed parameters are displayed and journaled. Strategies share simulated
liquidity. Sparse daily observations and approximate fills limit economic interpretation. The UI shows
point estimates, distinguishing forecast quality from PnL; no profitability certification is exposed.

## First feedback checkpoint

Try the path described in README.md. Record friction, unclear metrics, misleading data associations
and the next question the workbench should answer. Choose one research hypothesis before resuming
advanced development. Existing historical acceptance criteria remain future evidence requirements.
