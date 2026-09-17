# Strategy discovery: measured implementation state, 2026-09-13

> Latest delivery, 2026-09-14: beginner tutorial, interactive agent/finalist performance charts and
> the real R1 signal study are complete. Read [R1_RESULTS_2026-09-14.md](R1_RESULTS_2026-09-14.md)
> for the current outcome and next decision. Earlier evidence below remains historical.

**Discovery MVP delivered and verified.** D1 through D4 of PLAN_DISCOVERY_MVP.md are complete: the
Polymarket corpus, rule/parameter search, API, French interface, real campaign and both strict finalist
replays have been exercised. The application is ready for the first user feedback session.

**Feedback received and addressed:** the first campaign has no demonstrated edge. Automatic
post-campaign Codex interpretation is implemented and enabled locally; sparse binary mining horizons
are corrected in `discovery.v2`. Read the measured diagnosis and the next signal-first research
milestones in [POST_CAMPAIGN_REVIEW_2026-09-13.md](POST_CAMPAIGN_REVIEW_2026-09-13.md).

## Implemented and exercised

- Optuna parameter search plus actual symbolic conjunction mining, integrated with the existing engine.
- An initial fit prefix, three internal chronological training windows and frozen later validation.
- Independent candidate capital and liquidity; minimum five traded markets and activity in every
  training window; zero-volume carried rows excluded from mining support.
- Every trial and enumerated rule retained, including rejects and failures. Cancellation preserves
  partial results; interrupted attempts are retained and deterministic recomputation is explicit.
- HTTP campaign jobs, history, export and finalist replay. CLI: `pmx mvp search`.
- French UI with explanations, parameters, results by period, baseline without orders, coverage,
  cancellation and persisted history. Full source rule remains inspectable.
- Archive inventory, resumable download, checksums, hourly DuckDB adapter, censored-universe sidecars,
  RPC-backed settlement timestamps and loader/schema verification.
- Unknown expiry hidden from agent observations/calendar; unknown first quote hidden before bar
  completion; native USDC; archive provenance included in dataset identity.
- Engine 2.2.1 corrects fee quantity units: the quadratic binary model consumes whole contracts,
  notional and per-contract models consume milli-units. A real-fill regression proves 100 contracts
  at 0.90 USDC incur 0.18 USDC under the declared 20 bp scenario.

## Real campaign evidence

Initial campaign `c-ee460054342db202b7f5330d`, engine 2.2.0 before the Polymarket fee fix, ran on the
unchanged real `mvp2026` dataset hash
`201eb01fdcbd9485d07a1708bdb7b913d69b12d335b9a48aabdd0c8c03988eee`.
It used Kalshi, seed 7, six trials, maximum 60 markets, three training windows, two finalists and
100000 USD cents of initial capital per simulation.

Mining enumerated 500 hypotheses from 673 observed rows across 23 fit markets, accepted 306 as
fit-only proposals and retained 16 rules for the parameter search. These are no statistical promotions.
The first mined-rule strategy was rejected for insufficient distinct traded markets. Other trials
executed level, trend and reversal decisions. The two frozen finalists had later validation PnLs of
+2450 and -1783 USD cents. All training objectives were below the no-trade reference. This is evidence
of a functioning research process, not evidence of an economically robust strategy.

The real browser journey opened saved candidates, their replay and fills, launched seed 8 with
12 trials, requested cancellation, and reopened its persisted stopped state at 8/12 after reload.
Browser console reported zero errors or warnings. Screenshot:
`.scratch/discovery-replay-2026-09-13.png`. The repeat under engine 2.2.1 completed as
`c-f9b2c9cc8700422419f39134`, with identical Kalshi results. Both finalist journals passed strict
replay: `r-201eb01f-7-7344b904` and `r-201eb01f-7-49b2ff30`. Its full result is
`.scratch/discovery-final-real.json`.

## Verification

- Final whole suite: **1481 passed, 4 skipped, 0 failures/errors**, 451.257 seconds. The skips are
  explicitly opt-in live network probes. Evidence: `.scratch/discovery-final-tests.xml` and
  `.scratch/discovery-final-full-tests.log`.
- Includes discovery, nine new HTTP campaign tests, 13 archive tests, causal observation checks,
  fee accounting, journal replay, cancellation, cache/restart and unchanged legacy regressions.
- `ruff check src tests`: clean. `mypy src`: clean, 108 source files.
- After the binary journal-symbol compatibility correction, **333 targeted tests passed**: 212
  schema/integrity/runner tests and 121 journal/RNG tests. Evidence: `.scratch/discovery-symbol-tests.xml`
  and `.scratch/discovery-journal-tests.xml`. This includes the new boundary regression; it is not a
  second run of the whole suite. Both real Polymarket finalist journals passed strict replay afterwards.
- Frontend production build passes. Real responsive candidate views checked at 1440, 1024, 850 and
  390 CSS pixels; no global horizontal overflow. Wide period tables scroll within their own panel.
- A real archive build passed the strict canonical loader. The server independently loaded and
  verified the corpus; its UI shows 1018 train/validation markets and keeps the 255 sealed inaccessible.
- Initial server verification took about two minutes on this machine with other checks running.
  The verified corpus is then cached until restart; the UI explains the initial wait.
- The actual server was restarted after completion. Its persisted campaign, finalist and market replay
  reopened successfully; console errors/warnings: zero. Polymarket replay and campaign views at 390
  CSS pixels have no global horizontal overflow. Final screenshot:
  `.scratch/polymarket-discovery-completed.png`.

## Delivered Polymarket data

Pinned public source: `TimeSeventeen/Polymarket-v1`, revision
`5aa1b9d52316a8b2e789e81c8ae42c7ed532e8aa`. Initial inventory contains 1251 files and
13369088908 bytes. Full 2023 daily partitions are only about 12.4 MB; 2024 is 164.2 MB, 2025 1.608 GB,
and 2026 11.391 GB. The original full download is resumable but paused to prioritize an efficient
complete 2023 corpus. HF Xet stalled on this connection; verified HTTPS fallback worked.

Dataset `data/datasets/polyarchive2023`, UTC window 2023-01-01 through 2024-01-01 exclusive:

| Measure | Verified value |
|---|---:|
| Traded conditions in source window | 2423 |
| Source rows in window | 193374 |
| Conditions selected by outcome-blind SHA256 rank | 1500 |
| Selected source rows / observed hours | 113738 / 45396 |
| Eligible settled adapter markets | 1273 |
| Dense hourly bars / observed-volume hours in adapter | 365980 / 29644 |
| Training / validation / sealed | 763 / 255 / 255 |
| Source bytes needed, including explicit CTF projection | 39662850 |
| Dataset hashed files / bytes | 2833 / 115953274 |

Dataset hash: `06e90fa19a28b05c62d4456ef5d1fc4a9754472d185e188cc7bcaaa8f31c6e73`.
Selection preceded outcome eligibility checks. Exclusions: 193 right-censored at window end, four
without a resolution before the projection cutoff, 16 missing/ambiguous CTF preparations, 12
nonbinary/ambiguous payouts and two without a complete pre-resolution hour. These remain in the
archive evidence. The settled-only adapter is conditional and does not eliminate survivorship bias.

The CTF projection downloaded 27114253 bytes in 37 fragments plus two retained footers. All source
IDs were checked numerically against Polygon block 60000000 (verified UTC timestamp 1722368382000);
omitted row groups contain no earlier event. Exact HTTP 206 ranges, stable ETags, source-object
bindings, fragment hashes and cutoff evidence are retained and hashed with the dataset. Independent
code review and cache-tampering regressions checked this path. **Full CTF LFS hashes were not verified**;
this is explicitly partial-object provenance. The default full-object verification path remains intact.
All 1468 selected resolution block timestamps were obtained from verified Polygon RPC responses.

The 13.37 GB download remains paused and resumable: 496 inventory objects verified, 755 pending.
The bounded CLI recipe is in README.md. No full blockchain, historical order book, verified event
grouping, historically available expiry or historical fee reconstruction is claimed.

## Real Polymarket campaign

Campaign `c-42f3d0040baf469970c83d84` completed under engine 2.2.1: Polymarket, seed 7, 12 trials,
60 markets maximum per fold, three internal training windows, two finalists, 1000 USDC per simulation.
Fit mining enumerated 500 hypotheses, accepted 145 as fit-only proposals and retained 11 rules,
using 335 observed rows across 24 fit markets. These counts are search activity, not evidence of edge.
The complete campaign took about 5 minutes 47 seconds after cached dataset loading. Both frozen
finalists are reversal strategies. Every training objective was below the cash/no-order baseline of 0.
Later validation ran from 2023-07-26 through 2023-10-16 exclusive, with 60 sampled validation markets.

| Finalist | Training objective | Later PnL, USDC | Fees, USDC | Drawdown | Fills |
|---|---:|---:|---:|---:|---:|
| `strategy-b7877e19`, 4-bar reversal | -18.5833 | -26.87 | 5.30 | 2.71% | 525 |
| `strategy-046afa4c`, 2-bar reversal | -24.5000 | -21.95 | 4.68 | 2.23% | 449 |

These are negative exploratory results on a conditional sample. They establish a working search and
inspection path, not predictive advantage. Full campaign: `.scratch/discovery-polymarket-real.json`.
Finalist runs: `r-06e90fa1-7-42249c3d` and `r-06e90fa1-7-a9769aaf`.

Strict replay found and corrected a schema mismatch: binary provider IDs already allow 128 characters,
but `market_listed.symbol` capped their verbatim projection at 64 and refused Polygon's 66-character
IDs. The conditional reader bound now matches the source contract; continuous symbols stay capped at
64. A regression covers real-length identifiers and both maximum-length rejection boundaries. This
does not change execution or any stored event/hash. Both finalists passed strict replay with identical
reconstructed projection bytes. Evidence: `.scratch/discovery-polymarket-verification.json`.
The browser opened the real archive, its coverage report, the campaign and a finalist replay showing
four actual simulated fills, positions, forecasts and USDC amounts. Screenshot:
`.scratch/polymarket-finalist-replay.png`.

## Next research decisions after user feedback

The MVP searches price-based hypotheses and preserves its failures. It does not yet establish
statistical significance, model dependence between real events, or test executable order-book costs.
Only 29644 adapter hours have observed volume; carried prices are not additional independent evidence.
Questions/categories in the archive adapter are deliberately neutral, because historically available
semantic metadata is not verified. Human-readable retrospective metadata can be added separately.

Prioritize a preregistered signal study on a verified denser cohort: probability calibration, exact
24/48-hour reversals and causal activity conditions. Replicate effects before optimizing trading
parameters, then measure cost and exposure sensitivity. Reuse the same frozen evaluation protocol for
a small supervised challenger only if features show useful signal. The inspected 2023 validation
becomes development data; RL remains optional research, not the next delivery gate.

The local app is served at http://127.0.0.1:8175. Existing datasets and all prior changes remain intact.
There are no live orders, no downloaded model weights and no performance certification.

## Post-campaign analysis delivery

The user selected direct completion-triggered local Codex execution using their ChatGPT subscription.
The service now persists an evidence packet, analysis state, structured French review, Markdown and
CLI logs separately from the backtest. Completion enqueues a single review when enabled; repeated
completed requests reuse it. Analysis failures and interrupted attempts require manual retry and do
not fail the campaign. Old campaigns are not automatically backfilled. API and CLI cache hits do not
trigger new reviews. One local process owns a given results directory.

Actual login was verified as ChatGPT. The integrated review of `c-42f3d0040baf469970c83d84` completed
in about 71 seconds, attempt `a-84fdff6c9ee747e2801f3890b3df8554`, evidence SHA256
`8b64d2769c5f344d294cacd8b858703ec89fa075c2ea344ac5ee8a473d9cef97`.
Its artifacts are in `runs/mvp/analyses/c-42f3d0040baf469970c83d84/a-84fdff6c9ee747e2801f3890b3df8554/`.
A repeated real POST returned the same attempt. Markdown and evidence exports both returned HTTP 200.
The Codex event log contains the final agent message and usage, with no tool executions. A preliminary
manual smoke draft remains under `manual-initial/`; it is not the report selected by the application.

Verification for this addition:

- 173 focused tests passed: analysis lifecycle and subscription boundary, real campaign completion
  callback, HTTP/cache/restart, discovery, sparse-hour regression, rules and architecture.
  Evidence: `.scratch/postcampaign-tests.xml` (70.025 seconds).
- After adding the explicit CLI cache guard, all eight analysis/CLI tests passed, including two new
  CLI cases. Evidence: `.scratch/postcampaign-cli-tests.xml`. This is not another whole-suite run.
- Ruff passes; mypy passes for 111 source files. Frontend production build passes (39 modules).
- Actual browser report, six expandable findings, enabled checkbox, negative cash-baseline notice and
  exports verified. Desktop 1440px and mobile 390px have no horizontal overflow. Console: no errors or
  warnings. Screenshots: `.scratch/postcampaign-review-desktop.png`, `.scratch/postcampaign-review-mobile.png`.
- Real API/cache/export evidence: `.scratch/postcampaign-real-verification.json`.

The horizon fix changes symbolic target matching, not engine fills or prior artifacts. No new search
was launched to replace or conceal the negative results. R1-R3 remain the proposed research continuation.

## R1 delivery, 2026-09-14

The new `polyarchive2024h1` corpus passed pinned-source verification and the canonical loader. It
contains 1155 admissible settled markets (693/229/233 folds), with 59705 observed-volume hours among
469357 hourly bars: 12.72%, compared with 8.10% in 2023. Source and explicit CTF projection total
41018254 bytes. Corpus hash and retained exclusions are recorded in R1_RESULTS_2026-09-14.md.

Study `s-5aac7bec1fbc20e1d17d74aa` completed on January-March training observations, with a fixed
28-variant protocol and conservative historical ID protection. Its 601 observations retain missing
targets. One high-price calibration variant passes the descriptive screen; 27 remain inconclusive.
The candidate's 36 known outcomes and two missing labels do not establish a tradable edge.

New UI: a five-step beginner guide, return/capital/drawdown curves with date slider and visibility
controls, campaign finalist comparison, and the Signaux view with calibration/monthly plots,
activity conditions and downloadable observations. Capital, data identity, currency and common
validation universes are checked before plotting independent finalists together.

Validation: 39 targeted tests passed in 32.672 seconds (`.scratch/r1-final-tests.xml`), Ruff and mypy
passed (113 source files), production build passed (43 modules). These checks include causal
poisoning, exact-hour missingness, fixed anchors, protected metadata hashes, no held-out analytical
access, weekly-block/support guards, persistent API/cache/restart and existing campaign reviews.
The API reused the same real study and completion timestamp; both exports returned HTTP 200.
Evidence: `.scratch/r1-api-verification.json`, `.scratch/r1-independent-verification.json`.

Screenshots of the tutorial and comparative chart: `.scratch/r1-guide-mobile.png` and
`.scratch/r1-comparison-desktop.png`, `.scratch/r1-comparison-mobile.png`. Final signal screenshots:
`.scratch/r1-signals-desktop.png`, `.scratch/r1-signals-mobile.png`. Desktop 1440px and mobile 390px
signal views have no global horizontal overflow, including expanded protocol hashes. Wide result
tables scroll inside their panel. The guide closure survives reload and its reopening remains available.
Both activity conditions show 14 rows; selecting a hypothesis updates its monthly chart. A missing
month stays absent, with isolated observed points visible. Unsupported datasets disable R1 execution.
The final browser console reported zero errors or warnings after the rebuilt server and UI were loaded.
No new Optuna campaign, real order or promotion to R2 was executed in this milestone.
