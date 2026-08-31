All deliverables written and verified.

**Files delivered** (all under `C:/Dev/squad-ai/Brainstorming/GAN/Exchange`):
`docs/CONTRACTS.md` (1931 lines), `src/pxe/{types,events,rng,errors,__init__}.py` + `py.typed`, `schemas/observation.v1.json`, `schemas/action.v1.json`, `pyproject.toml`, `README.md`, `.gitignore`.

**Verified, not assumed**: `.venv/Scripts/python.exe -c "import pxe.types, pxe.events, pxe.rng, pxe.errors"` runs from the project root (I did `pip install -e . --no-deps --no-build-isolation` after adding setuptools/wheel; editable install resolves the src layout). Both schemas pass `Draft202012Validator.check_schema` and accept/reject sample payloads. All 24 event classes round-trip `to_dict`/`from_dict`/line. RNG output is identical across three subprocesses with different `PYTHONHASHSEED`. `pytest --collect-only` reads the config cleanly.

**Decisions a reviewer must challenge** (all also in CONTRACTS §12):

1. **`initial_cash_cents = 1_000_000`.** The PRD's "Cash initial 10 000" has no unit. Read as 10 000 contract units, not 10 000 cents; the latter caps an agent at 100 contracts while the standard MM quotes 25/side with `I_max=300`, which degenerates the arena.
2. **Zero floats in the journal.** Probabilities are `_ppm` ints, latent/signal values `_milli` ints, money `_cents` ints. `canonical_json()` raises on any float. Makes AC-P1 structurally safe rather than dependent on float repr; costs a conversion at the agent boundary and 1e-6 Brier granularity.
3. **Short position collateral is `100 x qty`, resting sell order collateral is `(100-p) x qty`.** FR-5.5.1's `(100-p)` is the incremental free-cash effect of an *unfilled* order; once filled the seller already holds `p x qty` in cash, so the escrow is the full payout. Together they reproduce FR-5.5.1 exactly. Also: **no netting** of a resting sell against an existing long (FR-5.5.2 "sum of worst cases"), which is over-conservative.
4. **Order-intent rejection is all-or-nothing on a collateral shortfall** (no silent quantity shrink), and **"atomically" in P3 means "not interleaved with another agent"**, not all-or-nothing for the block. Both were ambiguous in the PRD.
5. **The action schema is flat with all keys required and nullable types**, not `oneOf` on `op`. Strict structured-output engines handle that shape far more reliably; conditional semantics moved into `validate_action` (table in §7.14). Schema is 2.2 KB, self-contained, `additionalProperties: false` throughout.
6. **Frozen (bankrupt) agents get no observation and no gateway call**, so their Brier is a mean over fewer terms (reported as `n_terms`). Alternative would let a bankrupt agent farm a good Brier.
7. **Integrity incidents are not journalled** (offline detectors write `incidents.jsonl`), and **observations are hashed, not journalled** (`observations.jsonl`). Both keep detector/builder version bumps from moving a journal hash.
8. **Nothing wall-clock or provider-derived enters the journal** (latency, cost, tokens, retries go to `llm_trace.jsonl`) — this is what makes an LLM match still hash reproducibly for everything the engine decided.
9. **Resolution outcomes are published as HIGH-impact news**, so the MM widens after every resolution (FR-5.8.4). Defensible but a choice.
10. **`mm_initial_cash_cents` defaults to 10x an agent's cash** and enters invariant I2; without it the MM would be the binding liquidity constraint.
11. **The sync/async boundary is exactly one method**: `AgentGateway.collect_actions` runs `asyncio.run(acollect_actions(...))` and sorts replies by `agent_id`. The runner stays pure and synchronous (FR-5.1.2).

Also worth a look: the substream registry in `rng.py` is closed (unregistered names raise), with parametric families for `runner.tick_shuffle.<tick>`, `agent.<id>`, etc.; the P3 shuffle uses `fresh_substream` so it depends on `(seed, tick)` alone and not on prior draw consumption. Invariants I1..I11 are stated as checkable predicates in §6.2 and run every P4, not just in tests. Traceability in §11 covers all 35 FRs, AC-P1..P9, O1..O5 and all 30 WBS tasks, each mapped to an owning file and a named test.
