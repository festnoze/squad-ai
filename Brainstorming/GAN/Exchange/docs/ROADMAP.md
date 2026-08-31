# Remaining work

Written when the build was stopped at the end of wave 3. This file is the handover: it says what is left,
in enough detail that whoever picks it up does not have to reconstruct the plan.

`docs/CONTRACTS.md` stays the source of truth for how anything is built. `docs/BUILD_STATE.md` records the state
of the repository. This file records only the intent of the work that has not happened yet.

---

## 1. How the build was organised, and why to keep doing it that way

The whole system was built by agents working in parallel against one written contract. The mechanism that made
that work, and that the remaining waves should keep:

1. **One contract, written and adversarially reviewed before any implementation.** Three independent critics
   attacked it, and six of their findings were genuine contradictions that would have broken the parallel build
   (a float in `MatchConfig` that crashed the first event of every journal, three incompatible spellings of the
   canonical account order, a resolution-tick semantics that killed every default match at tick T).
2. **Exclusive file ownership.** Section 13 of the contract gives every file exactly one owning work package.
   Two packages never edit the same file, so nothing has to be merged by hand.
3. **Dependency layers, not a free-for-all.** A package only starts once the packages it imports are real code.
   Where two packages genuinely had to be written blind to each other (the runner and the observation builder),
   both coded against the contracted signature and an integration agent reconciled them.
4. **An integration gate closes every wave.** The gate may edit any file, resolves the "contract issues" list that
   every package reports, and drives the four checks green. This is where the defects that no single package can
   see get caught. In wave 1 the gate found a missing gateway reset hook that would have silently destroyed
   determinism for every LLM match with the whole suite green.
5. **No test is allowed to pass by being weakened.** Agents are told explicitly: never fix a failure by relaxing an
   assertion, adding a skip, or loosening a tolerance. The gate audits for tests that would pass against an empty
   journal.

Keep all five. The interesting failures in this project were all invisible to the package that caused them.

---

## 2. Wave 4: replay UI and the improvement loop

Two work packages plus a gate. The replay API (A22) is already done, so the UI has a real backend and real
generated fixtures to build on.

### A25 - `pxe.evolve`, the reflexive mutation pipeline (contract section 7.23)

Files owned: `src/pxe/evolve/{__init__,failures,mutate}.py`, `tests/test_evolve.py`.
Covers PRD section 8, WBS tasks T5.3 and T5.4, acceptance criterion AC-P8.

- `failures.py` extracts the `(scenario, seed)` pairs where the current champion underperforms beyond a threshold,
  and makes them replayable in one command. That is the Failure Hall of Fame the PRD asks for.
- `mutate.py` reads the traces of a harness's worst matches, proposes a patch to its prompt or config, creates a
  new version, has it validated by an A/B tournament, and **promotes only on a held-out gain**.
- The patch proposal is itself an LLM call, so it goes through `pxe.gateway.claude_cli` on `claude-sonnet-5`.
  Do not write a second subprocess path.
- AC-P8's bar: the child gains at least +1.0 mu TrueSkill against its parent on the held-out bank, at a per-match
  cost no worse than 110% of the parent's.
- Build and test the pipeline **offline and deterministically**: fake the patch-proposal call, and use scripted
  harnesses whose "prompt" is a config knob, so an A/B gain is reproducible without spending money.
- The promotion gate must be impossible to bypass. A child that wins on the training seeds but not on held-out
  must be rejected, and that must be a test.

### A24 - `web/`, the React + Vite + WebSocket replay UI (contract section 7.25)

Owns the whole `web/` directory and writes no Python. Covers PRD section 9, WBS tasks T4.2 to T4.5, AC-P7.

Six routes. What each must show:

- **Match view**: one panel per market with the price in cents over time and a simplified book, a scrolling news
  ribbon, and private-signal badges revealed after the fact (a replay spectator is omniscient).
- **PnL race**: one coloured line per agent, live ranking, annotated highlights (big trade, early resolution,
  integrity alert). Its final ranking must equal the accounting settlement to the cent (T4.3).
- **Decisions journal**: per tick and per agent, the predictions including the `carried` flag, the orders, the
  public message, and the harness reasoning excerpt when provided. With text search and tick-to-trade navigation.
- **Tournament view**: TrueSkill leaderboard with uncertainty, the MAP-Elites grid, per-version progression
  curves, integrity alerts, and the liquidity cost.
- **Share page**: standalone, read only, no token and no query string.
- **Match list**: the index.

Constraints that are acceptance criteria rather than taste:

- Eight agents must stay visually distinguishable, including under the common colour-vision deficiencies. That is
  what `components/colours.ts` is for, and it needs a test.
- Readable on a 13 inch screen.
- **AC-P7**: a newcomer identifies the winner and one reason in under 30 seconds. So the winner and the why must
  be the two loudest things on the page. `web/README.md` must carry the five-tester protocol.

A working reference already exists: the demo page built at the end of wave 3 renders a real match from the real
API payloads, including the PnL race, the five market panels, the tick-24 order book and the PnL-versus-Brier
chart. Read it before designing, then do better with live data and interaction.

### Wave 4 gate

Beyond the usual four checks and the `web` build and test:

- Verify T4.1 (under 100 ms per replay request), T4.3 (the UI ranking equals the settlement to the cent, proven
  against a real match rather than a fixture written to match), and that the share URL renders from the API alone.
- **Audit the API-versus-UI seam field by field against the running API, not against the fixtures.** Cents versus
  probability is the classic trap.
- Start the API and the UI for real and confirm the product actually works, not just that the tests pass.

### The nine contract issues A22 reported, still open

The replay API landed with a list. They are all real and the wave 4 gate should resolve each in the contract or
in the code:

1. **Fixture ownership contradicts itself.** Section 13 gives A24 the whole `web/` directory including
   `web/tests/fixtures/*.json`, but section 7.25 says those files are produced by `pxe api openapi --samples`,
   which is A22/A23 code. A24 cannot own a generated file it must not write. Fix the dispatch table, and make
   sure A24 does not hand-edit them: a UI test that passes only against a hand-edited fixture is worthless.
2. **`MarketTick.bids`/`.asks` is a real reconstruction living in the route layer.** No journal event carries book
   levels, so A22 folds `OrderPlaced`/`TradeExecuted`/`OrderCancelled` into per-price resting quantity inside the
   API. That is on the wrong side of rule 1 of section 7.21. Move the fold into `MatchProjection`, keep A22's
   cross-check against the journalled best bid, best ask and depth as a test, and confirm the payload is unchanged.
3. **The sample generator has no contracted signature.** Section 7.21 declares only `create_app` and
   `API_VERSION`, yet section 7.22 requires `pxe api openapi [--samples]`. A22 published
   `render_replay_api_markdown`, `write_sample_fixtures` and `payload_models`; put them in the contract.
4. **The tick clamp is self-contradictory**: `from_tick`/`to_tick` are said to clamp to `1..ticks_total` while
   ticks `0` and `ticks_total + 1` are said to be reachable and are the `/events` defaults. Resolved in code as
   `0..ticks_total+1`; write it down.
5. **`error` frame versus "closed immediately".** A bad `speed` sends one `error` frame then closes with 4400, so
   the UI's `socket.ts` must not assume an `error` frame implies a live socket.
6. **`Kpi.value_ppm` lies for five of the seven PRD section 15 KPIs**: `matches_per_night` is a count, two cost
   KPIs are milli-USD, the liquidity cost is cents. Either rename the field to `value` with `unit` authoritative,
   or split the ppm-only ones out.
7. **`heldout_gain_mu_milli` has no supplier.** No store reader exposes an evolve held-out delta; it is served
   as `0`. A25 should supply it.
8. **`AgentInfo.display_name`, `.kind` and `LeaderboardRow.ci_low`/`.ci_high` are undefined.** The API derives
   them (`"<agent_id> <harness_id>"`, `llm` if any action came from an LLM, `mu +/- 3 sigma`) and documents the
   derivations, but the UI will render numbers the contract never defined. Define them.
9. **`Elites.axes` and `.bins` have no persisted source.** `save_elites` stores cells only, no grid header, so
   axis names and bin counts are inferred. Persist the header.

---

## 3. Wave 5: adversarial acceptance and the honest verdict

Five auditors, then a fixer, then a verdict writer. The structure matters: the auditors are **read only** and
their instruction is to try to refute the claim that a criterion is met, not to confirm it.

### The five audit scopes

| Scope | What to attack |
|---|---|
| AC-P1 + AC-P9 | Determinism (byte-identical journals across machines) and guaranteed liquidity (two-sided MM quote on >= 95% of ticks with mute agents). Plus the M0 numbers: the 5 s match budget, the closed-system invariants at every tick, 10 000 orders per second. |
| AC-P2 + AC-P4 | The LLM match end to end, and score decoupling. AC-P2 needs real money, so verify everything that does not: the argv actually built, the schema actually passed, and a full 48-tick match against a fake CLI binary returning adversarial payloads. |
| AC-P3 + AC-P5 | 100 matches over >= 3 seeds per matchup with the Latin square, under the cost ceiling, report generated automatically. Held-out separation and the access log. Plus idempotent crash recovery without double counting. |
| AC-P6 + AC-P8 | Collusion precision and recall >= 0.9 on the cheater bench, false positives < 5% on an honest population. The mutation loop's promotion gate. **Check specifically whether the AC-P6 thresholds were tuned against the same set they are evaluated on**: if calibration and evaluation share a set, the number is not real. |
| AC-P7 + product | Build and serve the UI for real, judge whether the winner and the why are genuinely the loudest things, check colour distinguishability and the share page, and run every command in the README exactly as written. |

The auditor method that produced useful findings in earlier waves: for each test that claims to cover a
criterion, ask whether it would still pass against an empty journal or a stubbed return, whether it asserts the
PRD's actual number or a weaker one, whether the tolerance was chosen after seeing the result, whether it tests
the real code path or a mock of the thing under test, and whether the golden fixture was generated by the same
code it is meant to check.

### The fixer

Fixes the code, not the test. Strengthens any test weaker than the PRD and adds the control that proves it can
fail. Rejects bad findings with evidence, because auditors overreach. And for a criterion that genuinely cannot
be met by code alone, builds the honest artefact (the runnable command, the estimated cost, the human protocol)
and marks it **UNVERIFIABLE-BY-CODE**, never MET.

### The verdict

Re-verifies all nine criteria from scratch, trusting neither the auditors nor the fixer, then writes:

- `docs/ACCEPTANCE.md`: one section per criterion with the PRD wording, the verdict, the measured value against
  the required value, and the reproducing command. A summary table at the top, a milestone table for M0 to M5,
  and a "what costs money" section.
- `docs/STATUS.md`: what is implemented, what is deliberately out of scope, and the known limitations.
- A `README.md` in which every command has actually been run.

The standing instruction: an overstated verdict is worse than a red one. The entire premise of this system is
that no metric depends on a judge's opinion.

---

## 4. Two findings from the wave 3 demo that are open work

Both came out of one real scripted match and neither is cosmetic.

1. **The integrity detector produced a false positive on an honest table.** Six stock baselines, no cheaters, no
   channel between them, and `off_market_transfer` fired at high severity (A2 and A5 on M3 at tick 37, five
   trades up to 24 cents from the reference, 2 646 cents moved, scored 809% against a 300% threshold). One match
   is not a rate, but AC-P6 caps false positives at 5% of honest matches, so the threshold has to be calibrated
   against the honest bench rather than assumed. This belongs in the AC-P6 audit.

2. **The Brier ranking inverts the PnL ranking, and that is worth studying rather than fixing.** The PnL winner
   has the second worst calibration; the `mute` agent, which never trades, has the best. `zero_intelligence`
   scores exactly 0.250, the signature of declaring 50 cents everywhere against five YES outcomes. This is
   exactly the decoupling AC-P4 demands, and T5.6's Brier-versus-PnL analysis is where it should be written up.

---

## 5. What still costs money

Nothing above needs real LLM spend except two demonstrations.

| Demonstration | Calls | Estimated cost |
|---|---|---|
| AC-P2, one LLM match (4 LLM agents, 48 ticks) | ~192 | about 1.30 to 5 USD depending on the seat count |
| AC-P8, a mutation A/B with enough matches for a significant held-out TrueSkill gain | thousands | 200 to 400 USD |

Measured rate: about 0.027 USD and about 6 seconds per Claude CLI call in steady state, with roughly 35k cached
input tokens of unavoidable CLI overhead. That overhead is why the design makes one call per agent per tick
covering all markets at once, and why per-match budget caps are mandatory rather than advisory.

Every other acceptance criterion is verifiable for free with scripted agents.
