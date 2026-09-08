# pmx build handoff

Written 2026-09-08 when the user stopped the build at their usage limit. This file says exactly where the
multi-agent build stands and how to restart it at the same point. `docs/BUILD_STATE.md` (written by
gate G1) records the verified state up to the first real dataset; this file covers what happened after
it and what to do next. Delete or update this file when the build resumes.

---

## 1. Verified state on disk at the stop

Checked right after stopping every agent and process:

| Check | Result |
|---|---|
| `pytest -q -p no:warnings` (whole suite) | all green, no failure (about 650 tests, 4 legal `PMX_LIVE` skips) |
| `ruff check src tests` | clean |
| `mypy --strict` | clean, 49 source files |
| em-dash sweep | clean (tested by `tests/test_architecture.py`) |
| git | checkpoint commit `03a52dcd` made on 2026-09-08 at the resume (197 files, the whole v2 tree up to the C1b amendment and the data fixes). Later lots build on top of it. |

Documents: `docs/PRD_V2_HARD_OPTIMIZER.md`, `docs/PRD_V3_TRADING_OPTIMIZER.md`, `docs/PRD_V4_MULTI_ASSET.md`
(every market: six instrument kinds), `docs/PLAN_V2_WAVES.md` (part 1, waves 0 to 6),
`docs/PLAN_V3_WAVES.md` (part 2, waves 7 to 11, plus amendment C1b and the finance data wave 3b),
`docs/CONTRACTS_V2.md` (source of truth, sections 1 to 17, rulings R1 to R172 in sections 15.1 to 15.9),
`docs/BUILD_STATE.md`.

### Done

- Wave 0: contract, five schemas at `src/pmx/schemas/`, v1 frozen under `pmx.v1`, architecture and
  schema tests. Three critics, arbiter (R1..R85).
- Wave 1: data layer D1..D7 (types, errors, rng, journal, loader, schema, resample, builder, the Kalshi,
  Manifold, Polymarket and Metaculus importers, the news archive, lexicons at `src/pmx/lexicons/`, the
  data CLI `pmx.cli_data`, demo pack at `data/demo_v1/`). Gate G1 closed it (R86..R106) and proved AC-1
  on the fixture dataset `data/datasets/ac1_fixtures/`.
- Amendment C1 (section 16: `LiquidityModel` protocol and envelope, decision latency rule, clusters,
  opportunities, features, `torch_policy`; R107..R143 after one critic and an arbiter).
- Amendment C1b (section 17: six instrument kinds, integer price model, session calendars, cash
  events, per-kind forecast scores, per-kind claims; R144..R172). **Not yet adversarially reviewed**:
  the critic died on an OAuth expiry, the arbiter never ran.
- Data rulings R167..R170 implemented in `src/pmx/data/**`, `src/pmx/types.py`, the two lexicon maps
  `kalshi_series_subjects.v1.json` and `kalshi_series_categories.v1.json`.
- Real dataset `data/datasets/y2026/` rebuilt 2026-09-08 08:59 and sealed (hash `b760e08b...`): 67
  Manifold markets in three populated folds (train 42, validation 14, sealed 11), **0 Kalshi markets**,
  19 category fallbacks.

### Interrupted (lot 3c, run `wf_f8780559-b13`, stopped by the user)

- **C1b critic**: read-only, produced nothing; must be rerun in full.
- **Data-finish agent** (Opus, 99 tool calls): landed edits in `src/pmx/data/importers/kalshi.py`,
  `src/pmx/data/importers/manifold.py`, `src/pmx/data/builder.py`, `src/pmx/cli_data.py`,
  `tests/test_import_kalshi.py`, `tests/test_builder.py`. Its own notes, in order: "fix to the candle
  grid alignment", "walk floors in the importer and the CLI wiring", "new tests for the fixed
  behaviour". It did **not** rebuild the dataset and did **not** write its BUILD_STATE section. The
  tree is green after its edits, so the diagnosis of "Kalshi yields 0 markets" is: Kalshi candlesticks
  were not aligned to the daily bar grid (markets refused or `traded_bars` zero) and the settled walk
  lacked a window floor. Whether the fix is complete must be checked by rebuilding on one series.

---

## 2. Rules that govern the build (do not relax)

1. One contract, exclusive file ownership per package (contract section 13), gates that may edit
   anything and record rulings in section 15, no weakened test. See `docs/PLAN_V2_WAVES.md` header.
2. **One Workflow invocation per lot** (a wave's packages plus its gate, or smaller). Session quotas
   killed a 39-agent run (38 failures) and a 9-agent run (9 failures); nothing downstream survives a
   quota hit, but files written by finished agents do.
3. **Models**: implementation packages on Opus (`model: 'opus'`); gates, amendments, critics, arbiters
   and acceptance audits on Fable (omit `model`).
4. **Long network commands run in the background with a log and are polled**: an agent with no tool
   call for three minutes is killed as stalled (that is how the first data-fix agent died).
5. Package reports go to a JSON file in the scratchpad that the gate reads, never inlined at 70 KB.
6. Never the em-dash character in any produced content; English in code and docs.

---

## 3. Resume procedure

### Step 0: verify the tree

```
cd c:\Dev\squad-ai\Brainstorming\GAN\prediction_market
.venv\Scripts\python.exe -m pytest -q -p no:warnings
.venv\Scripts\python.exe -m ruff check src tests
.venv\Scripts\python.exe -m mypy --strict
git add -A && git commit -m "pmx v2: waves 0-1, amendments C1 and C1b, data fixes (build in progress)"
```

### Step 1: relaunch lot 3c (two agents in parallel, then the arbiter)

The script of the stopped run is at
`C:\Users\e.millerioux\.claude\projects\C--Dev-squad-ai-Brainstorming-GAN-prediction-market\d4f591f7-af6d-4365-8066-f97d28622148\workflows\scripts\pmx-lot3c-c1b-review-datafinish-wf_f8780559-b13.js`.
Rerun it as is (its prompts already carry the background-and-poll rule), or rewrite it with the same
two tasks:

- **C1b critic then arbiter** (Fable): lens = contradictions with sections 1, 5, 8, 9, 12, 16; leaks
  through cash events, rolls, calendars, horizon resolutions, derived wiki subjects; feasibility for
  E1, E2, E3, E5 from sections 16 and 17 alone; rulings R167..R170 matching the code. Arbiter records
  rulings continuing 15.9 and never leaves stale normative text.
- **Data finish** (Opus): confirm the candle grid alignment and walk floor fixes are complete and
  tested; reproduce on one Kalshi series from the HTTP cache `data/datasets/y2026/cache/`; rebuild in
  the background (`pmx.cli_data build`, providers kalshi,manifold, freeze 2026-09-07, 365 days,
  `--keep-self-resolved`, series list `data/datasets/y2026/kalshi_series.txt`, limit 400 per provider,
  `PMX_USER_AGENT_CONTACT=etienne.millerioux@studi.fr`, `--force --seal`), poll the log, verify, report
  counts (per provider, per fold, per category, per month, removed per filter, `n_bars_only`,
  `n_category_fallback`, linked news), append a dated section to `docs/BUILD_STATE.md`.

### Update 2026-09-08 evening: lot 4 outcome and the v5 revision

Lot 4b finished the four engine packages (E1 80 tests, E2 88, E3 63, E5 39; E4 46 from lot 4) with 60
contract issues between them; gate G2 died on the session limit after creating `src/pmx/data/sessions.py`.
The engine files are uncommitted on top of `2659b1d9`. The user then challenged the product and validated
PRD v5 (`docs/PRD_V5_DISCOVERY.md`: sensor gene, hypothesis layer with tested rules, minute grids with
timestamped sources, workflow agents). The plan (`docs/PLAN_V3_WAVES.md`) now carries amendment C1c and
the revised wave 5 and later waves. **Next launch order (revised by `docs/REVIEW_2026-09-08.md` and plan part 3)**: (1) gate G2 alone, reading the E4 report in the
scratchpad and the four finish reports in the `wf_49cf644e-c62` journal, and applying the E1 hook (the
observation builder takes a per-agent sensor set); (2) amendment C1c extended by the review decisions, with one critic and an arbiter;
(3) lot 5b, measure first: DS1, S1, S2, R2a..R2e, F1..F5, U1, U2, then gates G3 and G3b; (4) lot 6: agents for the measured edges, optimizer with two-tier fitness, live; (5) lot 7: surfaces with the guided tour.

### Step 2: lot 4, the engine wave (done except gate G2, see the update above)

E1..E5 on Opus in parallel, then gate G2 on Fable. Build against sections 16 **and** 17. The previous
engine script (`pmx-v2-wave2-wf_4922d436-84f.js` in the same scripts directory) has the five package
prompts and the G2 prompt; drop its G1 and C1 phases and add "section 17" to every package's reading
list, plus the 17.9 deferrals list as G2's explicit to-do (types additions, `journal.v2.json` `oneOf`
promotion with the dataclasses, settle-phase enum, `market.v2.json` and `dataset.v1.json` widenings,
loader walking `instruments/` and `calendars/`, `pmx/__init__.py` schema constants).

### Step 3: lot 5, agents and finance data in parallel

A1..A6 plus U1, U2 (part 1 wave 3) and F1..F4 (part 2 wave 3b) on Opus, then gates G3 and G3b on
Fable (G3b writes and runs `tests/e2e/test_e2e_1b_multi_asset.py`). A1 also adds the `carry`, `basis`,
`pairs`, `vol_regime`, `calendar` and `random_walk` families of PRD v4.

### Step 4 onward

O1..O4 plus L1, gate G4 (also `tests/e2e/test_e2e_0_base.py` per R137). U3, U4, gate G5 (README rewrite
must mention PRD v3 and v4 and the honesty section). Then part 2: waves 7 to 11 of
`docs/PLAN_V3_WAVES.md`, each opened by its amendment (C2..C5, Fable, one critic) and closed by its
gate running `tests/e2e/` in full. Final: the acceptance audit (three auditors on Fable, AC-1..AC-25),
fix agents, re-audit.

---

## 4. Open defects and decisions pending

- Kalshi markets still absent from the real dataset (diagnosis above; fix landed but unverified).
- Wikipedia items linked to zero markets in the 08:59 build; R169's linker renormalisation and derived
  subjects should change that, to be confirmed by the rebuild.
- Section 17.9 lists everything C1b deferred to gate G2 with owners; G2 must apply all of it.
- `README.md` still describes v1 plus a v2 pointer; U4 rewrites it.
- The Polymarket importer is evidence of the ANJ block only; Polymarket markets never enter a built
  dataset (R105) until a size-carrying tape is reachable.
- Yahoo is the only equities and futures tape and is unofficial; every finance manifest must label
  `vendor: "yahoo"` (PRD v4 section 2).

---

## 5. Previous workflow runs (for `resumeFromRunId` or reading journals)

Scripts under `C:\Users\e.millerioux\.claude\projects\C--Dev-squad-ai-Brainstorming-GAN-prediction-market\d4f591f7-af6d-4365-8066-f97d28622148\workflows\scripts\` (some under the sibling `...-GAN-prediction-market-docs\...` directory); journals under
`C:\Users\e.millerioux\.claude\projects\c--Dev-squad-ai-Brainstorming\d4f591f7-af6d-4365-8066-f97d28622148\subagents\workflows\<run>\journal.jsonl`.

| Run | Content | Outcome |
|---|---|---|
| `wf_298a3b7d-2e8` | whole build in one go | 38 of 39 agents died on the session limit; C0 landed |
| `wf_97767d8f-d17` | 3 critics, arbiter, D1..D7, G1 | all but G1 done; 3.4 M subagent tokens |
| `wf_4922d436-84f` | G1, C1, E1..E5, G2 | all 9 died on the session limit |
| `wf_7555466c-a60` | G1 finish, C1, critic, arbiter | all 4 done |
| `wf_a85d5408-539` | C1b, data fixes, critic | C1b done; data agent stalled; critic OAuth failure |
| `wf_f8780559-b13` | C1b critic, arbiter, data finish | stopped by the user mid-way |
