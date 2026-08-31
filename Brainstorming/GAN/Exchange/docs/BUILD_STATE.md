# Build state

Stopped on request at the end of wave 3. What remains is described in `docs/ROADMAP.md`.
`docs/CONTRACTS.md` is the source of truth for how anything is built.

## Gate

| Check | Result |
|---|---|
| `python -m pytest -q` | 1055 passed, 6 skipped, 0 failed (22 min, measured by the wave 3 gate) |
| `python -m pytest -q -m "not slow and not llm"` | 1020 passed, 41 deselected (4 min, verified independently after the gate) |
| `python -m ruff check src tests` | clean |
| `python -m ruff format --check src tests` | 128 files already formatted |
| `python -m mypy src/pxe --strict` | no issues in 79 source files |

The 6 skips are deliberate and documented: 5 opt-in paid LLM tests (`PXE_LLM_E2E=1`, about 1.30 USD each) and one
Postgres schema comparison (`PXE_TEST_POSTGRES_URL`).

## Work packages

**Landed and green (23 of 25):** A01 anchor, A02 journal, A03 world, A04 info, A05 exchange CLOB, A06 accounts and
fees, A07 market maker, A08 oracle, A09 runner, A10 observation builder, A11 action validator, A12 baselines,
A13 gateway protocol, A14 Claude CLI adapter, A15 metrics projection and performance, A16 calibration,
A17 behavioural descriptors, A18 integrity detectors and cheater bench, A19 tournament orchestrator, scheduling
and Latin square, A20 ratings, elites, both Halls of Fame and the held-out bank, A21 store, A22 replay API,
A23 CLI and tournament report.

**Not started (2):** A24 the React replay UI, A25 the reflexive mutation pipeline. Both are specified in
`docs/ROADMAP.md`.

## Milestones

| Milestone | Content | State |
|---|---|---|
| M0 engine | Epic E1 | cleared and measured |
| M1 LLM agents | Epic E2 including the blocking T2.6 market maker | cleared, except the paid end-to-end match, which is written but not run |
| M2 tournaments | Epic E3 | cleared |
| M3 replay | Epic E4 | API done, the React UI is not built |
| M4 optimisation | T5.1 to T5.4 | descriptors, MAP-Elites and the Failure Hall of Fame are in; the mutation loop is not |
| M5 integrity | T5.5 to T5.6 | cleared |

## Measured acceptance numbers

Measured by the wave gates on real runs, not claimed.

| Criterion | Bar | Measured |
|---|---|---|
| AC-P1 determinism | byte-identical journal | 3 golden journals identical across `PYTHONHASHSEED` unset / 0 / 12345, from a fresh subprocess |
| M0 speed | 6 agents x 48 ticks under 5 s, no LLM | 1.30 s |
| FR-5.5.3 closed system | no breach | 48 of 48 ticks, 0 breaches |
| AC-P9 guaranteed liquidity | two-sided quote on >= 95 % of ticks with mute agents | 100 % of market-ticks; reference price defined on 240 of 240 |
| CLOB throughput | >= 10 000 orders/s | 41 520/s matching, 16 185/s end to end with the journal |
| AC-P3 nightly tournament | >= 100 matches, >= 3 seeds per matchup, auto report | 112 matches, 28 matchups, 4 seeds each, Latin square with max deviation 0, reports written unattended, 373 s, 38 MiB peak, 0.00 USD |
| AC-P4 score decoupling | proven in both directions | rewrite predictions and performance is byte-identical; rewrite trades and calibration is byte-identical |
| AC-P5 held-out | separated, every access logged | disjoint train and sealed seed sets, a training draw refused and logged |
| AC-P6 integrity | precision and recall >= 0.9, false positives < 5 % | precision 1.000, recall 1.000 on the held-out cheater set; honest false positives 0.0000 to 0.0067 |
| T3.2 ratings | sigma decreasing, expected order recovered | sigma 8.333 to 0.68-0.74 over 200 matches, ladder order recovered exactly |
| T5.1 descriptor stability | inter-seed correlation > 0.6 | 0.844 worst to 1.000; erratic control at -0.141 |
| T4.1 replay latency | < 100 ms per request | p50 2.52 ms, p95 3.68 ms in process; 5.84 / 7.20 ms over HTTP |
| FR-5.8.6 liquidity presets | base spread within 1 c of the preset | 4.000 / 5.998 / 11.984 c over 200 matches per preset, two-sided on 99.98 to 100 % |

Not yet demonstrated: **AC-P2** (one real LLM match, about 1.30 to 5 USD), **AC-P7** (five human testers) and
**AC-P8** (the mutation loop, 200 to 400 USD). See the cost table in `docs/ROADMAP.md`.

## Defects the gates caught that no single work package could see

Worth reading before adding to this codebase: every one of these passed its own package's tests.

- **Wave 1.** `AgentGateway` had no reset hook, so the runner reflected on private attributes and guessed
  `agents` / `_agents`; `ClaudeCliGateway` exposes `harnesses`, so determinism would have died silently for every
  LLM and mixed match with the whole suite green. A cancelled market was advertised as tradable and leaked a
  private signal, invisible because all three templates ship no cancellations. Four dataclasses validated market
  order with lexicographic `sorted()`, which rejects correct input at ten or more markets.
- **Wave 3.** `HeldoutBank.reserve` drew seeds over `2**64` while `BigInteger` is signed, so about half of every
  sealed set raised `OverflowError` and AC-P5 could not run. No tournament ever wrote an `elite_cell`, so T5.2's
  grid existed only in a test fixture. `docs/MM_LIQUIDITY_COST.md` was generated by a test-private flow that
  publishes no news, so FR-5.8.4 never fired and a failing spread criterion was published as passing: through the
  shipped command the effective spread is 1.351 c (standard) and 3.146 c (illiquid), not 0.
- **Vacuous tests found and given teeth.** The fee arm of every metric was structurally zero because all three
  goldens run at zero fees, so a projection that dropped the fee term passed everything. `write_meta` and
  `read_meta` were only ever tested against each other while the runner writes the real file. Six dead
  `importorskip` guards would have silently skipped on a broken import. A18's calibration and evaluation seed
  split was a convention rather than a checked invariant, which would have let a recycled tuning seed turn AC-P6
  into a claim about its own training data.

## Product demo

A demo page rendering one real match through the real replay API was published during wave 3. It shows the PnL
race, the five correlated markets, the order book at tick 24 and the PnL-versus-Brier chart, with every number
projected from the journal. Two open findings came out of it and are carried in `docs/ROADMAP.md` section 4:
an integrity false positive on an entirely honest table, and the Brier ranking inverting the PnL ranking.

## Restart

Wave 4 (A25, then A24, then an integration gate) and wave 5 (five adversarial acceptance auditors, a fixer, then
the verdict) are specified in `docs/ROADMAP.md`, including the nine open contract issues the replay API reported.
