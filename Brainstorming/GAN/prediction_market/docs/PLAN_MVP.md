# pmx: MVP delivery plan, 2026-09-13

> This first workbench has been delivered. The active continuation is [PLAN_DISCOVERY_MVP.md](PLAN_DISCOVERY_MVP.md).

## Authority and purpose

The user explicitly authorized a complete reprioritisation on 2026-09-13 after the critical review.
This document replaces the remaining order in PLAN_V2_WAVES, PLAN_V3_WAVES and HANDOFF. The historical
STATE_2026-09-13 remains the starting snapshot, not a claim about the current working tree.
CONTRACTS_MVP.md is the scoped amendment to CONTRACTS_V2.md. Existing contracts remain in force where
the amendment does not explicitly supersede them. No old cohort, tour, multi-asset or optimizer gate
blocks this MVP. No statistical certification threshold is reduced to obtain an MVP pass.

The goal is a complete local research workbench the author can use and give feedback on. The first
release must answer: can I understand the data, run a comparison, inspect what each strategy did,
and tell prediction quality apart from simulated money? It does not certify profitable trading.

## MVP user journey

1. Start the application with one documented command or the Windows launcher.
2. See the actual research dataset, its providers, date span, grid, split counts and limitations.
3. Search and filter markets, open a market, inspect its actual price/volume history and dated news.
4. Choose a provider, training or validation slice, strategies, seed, bankroll and a bounded sample.
5. Launch a background backtest through the v2 engine and see running, completed or failed state.
6. Compare forecast skill, net simulated PnL, fees, drawdown and trade counts, with the market baseline.
7. Open a run and inspect forecast/price overlays, positions and fills; reload or export the result.

Default interface copy is French. Code and technical documentation remain English. There is no
automatic network fetch, no demo-data substitution and no automatic use of the sealed slice.

## Delivery phases and acceptance

| Phase | Deliverable | Exit evidence |
|---|---|---|
| M0: scope and contracts | This plan, the MVP amendment, updated entry points, explicit deferred backlog | One active sequence and agreed backend/frontend payloads on disk |
| M1: usable data and safe runs | Taxonomy wiring, a new verified derivative of the existing real snapshot, roster-aware run identity, rule-label availability regression | Dataset verifies without changing the original; same inputs replay; a different roster does not collide; future results do not alter past rule records |
| M2: runnable backend | Small genuine scripted roster, bounded background run API, persisted history/results and CLI | API integration test builds data, runs the engine, reads results and replays the journal; invalid requests fail visibly |
| M3: complete frontend | Dataset overview, filtered market browser, run configuration, result table and replay | TypeScript/build pass; browser completes the real user journey including run launch, reload and error states |
| M4: integration and handover | Launcher, README, measured status and first real sample run | Relevant regression suite, full backend suite once, lint/types, production web build, real browser smoke and saved evidence |
| Feedback checkpoint | Author tests the MVP | Collect friction, missing decisions and the next highest-value experiment before advanced work |

M1, M2 and M3 may overlap after M0 with exclusive ownership. Integration is continuous; the browser
must consume the real backend before the final phase. Only one worker runs the full Python suite.
Small targeted tests run with each change. Mutation checks are used for critical numerical/as-of
regressions; tests must continue to detect incorrect behaviour rather than merely mirror new code.

## Ownership for this delivery

| Work package | Owned files |
|---|---|
| Data | src/pmx/data/{builder,loader,prepare_mvp}.py, src/pmx/data/schema.py, src/pmx/types.py taxonomy fields only, src/pmx/schemas/market.v2.json, relevant data tests, new derivative dataset |
| Backend | src/pmx/agents/*, src/pmx/api/*, src/pmx/cli_mvp.py, tests/test_mvp_api.py, tests/test_mvp_agents.py |
| Frontend | web/src/*, web/vite.config.ts, web/index.html, web/package.json if needed |
| Integration owner | docs/*, README.md, launch scripts, src/pmx/cli.py, runner identity/version changes and their tests, rules/tester.py and its regression tests, integration evidence |

Cross-package changes are coordinated with the integration owner. The old model names and Workflow
invocation quotas are historical operational notes, not constraints on the current toolchain. Use up
to three independent workers plus the coordinator when useful, with no concurrent full test suites.
No commits, pushes, external deployment or real trades are required for this delivery.

## Deliberate scope boundaries

Included: binary Kalshi and Manifold data already on disk, daily bars clearly labelled as such,
provider-separated runs, train/validation exploration, fixed transparent scripted strategies,
integer accounting, data provenance, persisted journals, replay and a functional local interface.

Deferred until feedback: complete eleven-family registry, learned calibration, shared memory/hive,
rule mining in the trading path, automated search and MAP-Elites, statistical claims ledger, LLMs,
live forecasting service, hourly/minute network rebuilds, forty-cohort coverage, multi-asset importers,
GPU/RL, adversarial market maker, advanced portfolio allocation, guided tour and showcase collection.
Existing infrastructure is retained. Unsupported features are not represented by dead navigation.

## Post-MVP priorities

1. Fix usability issues from the first test and define one concrete research hypothesis.
2. Re-probe Kalshi historical trades, measure source timestamps and start prospective data capture.
3. Improve execution realism and quantify uncertainty using independent events and adequate support.
4. Add simple supervised baselines and bounded parameter search; compare quality per compute budget.
5. Add memory, information sources and sharing one at a time with controlled ablations.
6. Open evolution, broader assets, LLMs or adversarial training only when an experiment motivates them.

Historical AC-1 to AC-36 remain backlog references. M0 to M4 are delivery milestones, not replacements
for the future evidence required by a scientific or economic claim. Forty cohorts and thousands of
markets measure coverage; they do not by themselves establish statistical power.

## Working status

- M0: complete. Active scope, priorities, ownership and payload contract written.
- M1: complete. All 287 markets retained in a verified derivative; identity and as-of guards tested.
- M2: complete. Real roster, API, background jobs, persistence, exports and CLI implemented and tested.
- M3: complete. Frontend built and exercised against the real API, including a 12-market experiment.
- M4: complete. Launcher, README, targeted/full-suite evidence and browser findings are in MVP_STATUS.md.
- Next: author feedback on the runnable MVP, before any advanced implementation.
