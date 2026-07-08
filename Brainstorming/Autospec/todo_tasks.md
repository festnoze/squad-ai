# todo_tasks.md — Verified Swarm Upgrade execution tracker

**Source plan:** [VERIFIED_SWARM_UPGRADE.md](VERIFIED_SWARM_UPGRADE.md) (v2.1)
**Branch:** `verified-swarm-upgrade` (off `main`)
**Role:** single synchronizer for parallel agents. Before starting a task, set its status to `WIP` and add your agent id. On completion set `DONE` and tick its acceptance box. Never start a task whose deps are not `DONE`.

## Legend
- Status: `TODO` · `WIP` · `DONE` · `BLOCKED`
- **Isolation:** `NEW` = touches only new files → worktree/parallel-safe · `SHARED` = edits a hot shared file (`config.py`, `pipeline.py`, `models.py`, `delivery_gate.py`, `refine.py`) → must run **sequentially on the feature branch**, never in a parallel worktree.
- Conflict policy: all `SHARED` tasks are serialized by the orchestrator (me). `NEW` tasks may be fanned out to parallel agents. `config.py` field additions are batched per wave in a single edit to avoid churn.

## Hot-file ownership (conflict map)
| File | Waves that touch it | Rule |
|---|---|---|
| `config.py` | all | one batched edit per wave, sequential |
| `orchestrator/pipeline.py` | 0,0.5,1,2,3,4,5 | sequential only; the dev-loop hot path (~2952–4161) is single-writer |
| `models.py` | 0,4 | small additive edits, sequential |
| `orchestrator/build_monitor.py` | 0,0.5,1,2 | additive event kinds/fields, sequential |
| `orchestrator/delivery_gate.py` | 2,3 | sequential |
| `orchestrator/refine.py` | 1,2 | sequential |
| `agents/prompts.py`, `agents/personas.py` | 1,2,3,5 | additive (new personas/prompts), low conflict, sequential |
| new modules (`recovery.py`, `arbitration.py`, `constitution.py`, `amendment.py`, `scorecard.py`, `guards.py`, `signatures.py`, `schema.py`) | — | `NEW`, parallel-safe |

---

## Wave 0 — Verified preset + baseline telemetry  ·  status: DONE (impl+tests; W0.6 baseline deferred to a real run)
Foundational. All `SHARED`; done first, sequentially. Unblocks every KPI comparison.

| ID | Task | Files | Isolation | Deps | Status |
|---|---|---|---|---|---|
| W0.1 | `PRESET=verified` env preset enabling the existing gauntlet (REFINE, REVIEW_PLAN, RUNTIME_ACCEPTANCE, COVERAGE, MUTATION, DOD_STRICT_CRITERIA, EVALUATOR, SECURITY_REVIEW). Impl'd as a quality overlay in `Settings.__post_init__` (overrides `.env` defaults, yields to a shell override) — cleaner than a product profile and needs zero call-site changes. | `config.py` | SHARED | — | DONE |
| W0.2 | KPI analyzer over `build-monitor.jsonl` → green@1, attempts/story, failed, tokens/green, wall-clock, per-model breakdown. CLI `python -m autospec.orchestrator.scorecard`. | `orchestrator/scorecard.py` (NEW) | NEW | W0.3 | DONE |
| W0.3 | Record resolved `model` on every call: field on `BuildMonitor.agent_call` + `AgentInteraction` + set at `_UsageTracker.arun` (both ok/error paths) | `build_monitor.py`, `models.py`, `interactions.py`, `pipeline.py` | SHARED | — | DONE |
| W0.4 | Context-budget telemetry: `_check_context_budget` logs prompt size + warns near `CONTEXT_WARN_CHARS` | `pipeline.py`, `build_monitor.py`, `config.py` | SHARED | W0.3 | DONE |
| W0.5t | Tests: preset overrides/yields (clean subprocess), scorecard KPIs on a fixture timeline, model field on the interaction record | `tests/test_scorecard.py` (NEW) | NEW | W0.1–W0.4 | DONE (9 pass; full suite 625 pass) |
| W0.6 | Run one real project under `verified`; archive baseline JSONL + KPI snapshot | `docs/baselines/` | — | W0.1–W0.5t | DEFERRED (needs a live agent run) |

**Acceptance:** ☑ preset toggles all gates ☑ scorecard emits KPIs ☑ every call logs its model ☐ baseline archived (needs live run)

---

## Wave 0.5 — Anti-cheating guards & harness hardening  ·  status: TODO
Before W1: the recovery machine needs honest, flake-free, schema-valid signals. Guards are mostly `NEW` (detect logic) + a thin `SHARED` hook in the dev loop.

| ID | Task | Files | Isolation | Deps | Status |
|---|---|---|---|---|---|
| W0.5-SIG | Failure-signature normalizer (test node id + exception type; guard verdicts `tampered`/`out_of_scope`/`skeleton`) | `orchestrator/signatures.py` (NEW) | NEW | — | TODO |
| W0.5-T05 | Test-tamper guard: detect dev edits to QA test files via `git diff --name-only`; revert + flag | `orchestrator/guards.py` (NEW) | NEW | — | TODO |
| W0.5-T06 | Scope guard: post-hoc file-claim enforcement (warn/strict) reusing `independence.py` claims | `orchestrator/guards.py` (NEW) | NEW | — | TODO |
| W0.5-T07 | Skeleton detector: AST/grep for pass-only bodies, hardcoded test literals, skip/xfail insertions | `orchestrator/guards.py` (NEW) | NEW | — | TODO |
| W0.5-T09 | Schema-validated decision outputs: wrapper around `extract_json` with per-call schema + retry-once | `orchestrator/schema.py` (NEW) | NEW | — | TODO |
| W0.5-T08 | Flaky-check quarantine: rerun a red test once before it counts; quarantine flip-floppers | `pipeline.py` (`_arun_pytest` caller), `config.py` | SHARED | W0.5-SIG | TODO |
| W0.5-T10 | Hallucinated-import guard: imports must resolve to manifest/stdlib | `orchestrator/guards.py` (NEW), hook in `pipeline.py` | SHARED | — | TODO |
| W0.5-HOOK | Wire tamper/scope/skeleton guards into the dev loop (pre-`_arun_pytest`); flags gate each | `pipeline.py`, `config.py` | SHARED | T05,T06,T07 | TODO |
| W0.5-T11 | Golden-transcript CI harness: record `fake_agents`/FakeRunner scenario transcripts as goldens | `tests/golden/` (NEW), `tests/test_golden.py` | NEW | — | TODO |
| W0.5t | Unit tests for each guard + schema wrapper + flake rerun | `tests/test_guards.py`, `tests/test_schema.py` (NEW) | NEW | above | TODO |

**Acceptance:** ☐ dev editing a QA test is reverted ☐ out-of-scope diff flagged ☐ skeleton impl flagged ☐ flake not counted ☐ decision JSON schema-validated ☐ hallucinated import caught ☐ goldens in CI

---

## Wave 1 — Recovery state machine + escalation ladder  ·  status: TODO
Deps: **W0.5-T08 (flake filter), W0.5-T09 (schema), W0.5-SIG**. Core is `NEW` + pure-unit-testable; integration is `SHARED`.

| ID | Task | Files | Isolation | Deps | Status |
|---|---|---|---|---|---|
| W1.1 | `recovery.py`: pure state machine `next_action(history) → RETRY/ESCALATE/CLASSIFY/SPLIT/ARBITRATE/AMEND_PROPOSAL/FAIL`; `TaskFailureHistory` dataclass | `orchestrator/recovery.py` (NEW) | NEW | W0.5-SIG | TODO |
| W1.2 | Escalation ladder config + `_FORCE_MODEL` contextvar honored in `_UsageTracker.arun` | `config.py`, `pipeline.py` | SHARED | W1.1 | TODO |
| W1.3 | Root-cause classifier call (boss-tier) + `classifier` persona/prompt; schema-validated (W0.5-T09) | `orchestrator/recovery.py` or `classifier.py` (NEW), `personas.py`, `prompts.py` | NEW+SHARED | W1.1, W0.5-T09 | TODO |
| W1.4 | Refactor dev-loop decision points to delegate to `recovery.next_action` (byte-identical when flags off) | `pipeline.py` | SHARED | W1.1,W1.2,W1.3 | TODO |
| W1.5t | Tests: full transition matrix (pure); flags-off = legacy sequence; ladder climbs model; classifier consulted at exhaustion | `tests/test_recovery.py` (NEW) | NEW | W1.1–W1.4 | TODO |

**Acceptance:** ☐ machine reproduces legacy retry→split→fail when off ☐ ladder climbs on retry ☐ classifier routes stuck tasks ☐ infra errors don't consume rungs

---

## Wave 2 — AC↔test traceability + wrong-test arbitration  ·  status: TODO
Deps: **W1** (classification is the only entry to arbitration).

| ID | Task | Files | Isolation | Deps | Status |
|---|---|---|---|---|---|
| W2.0a | Require AC-id marker in QA tests (prompt) + marker parser | `prompts.py`, `orchestrator/traceability.py` (NEW) | NEW+SHARED | — | TODO |
| W2.0b | Delivery-gate check: every AC has ≥1 executed test; flag orphan tests | `delivery_gate.py`, `orchestrator/traceability.py` | SHARED | W2.0a | TODO |
| W2.1 | `arbitration.py`: `aarbitrate_test(...) → {fix_impl/fix_test/spec_contradiction}` (boss-tier `arbiter`); schema-validated | `orchestrator/arbitration.py` (NEW), `personas.py`, `prompts.py` | NEW | W0.5-T09 | TODO |
| W2.2 | Wire rulings into loop: fix_impl→one guided top-rung attempt; fix_test→checker QA-fix (bounded `arbitration_max`); spec_contradiction→W5 | `pipeline.py`, `refine.py`, `config.py` | SHARED | W1.4, W2.1 | TODO |
| W2.3 | Surface arbitration events (interactions + BuildMonitor + Activity.tsx) | `pipeline.py`, `interactions.py`, `frontend/src/components/Activity.tsx` | SHARED | W2.2 | TODO |
| W2.4t | Tests: orphan-test → fix_test → green; fix_impl path; 2nd fix_test refused; infra flake never arbitrated; constitution tests never targeted | `tests/test_arbitration.py`, `tests/test_traceability.py` (NEW) | NEW | W2.0–W2.3 | TODO |

**Acceptance:** ☐ every AC mapped to a test ☐ orphan tests flagged ☐ wrong test → fix_test → green ☐ fix_test bounded ☐ deterministic failures never arbitrated

---

## Wave 3 — Constitution compiler  ·  status: TODO
Deps: none hard (slots after SPEC). Interacts with W2 (constitution tests immutable to fix_test) and W5 (immutable rules non-amendable).

| ID | Task | Files | Isolation | Deps | Status |
|---|---|---|---|---|---|
| W3.1 | Constitution phase (boss-tier) between SPEC and PLAN → rules `{id,statement,kind,immutable}` | `orchestrator/constitution.py` (NEW), `pipeline.py`, `prompts.py` | NEW+SHARED | — | TODO |
| W3.2 | Compiler: rule→pytest file under `tests/constitution/` OR delivery-gate command; non-compilable → advisory (prompt-injected) | `orchestrator/constitution.py` | NEW | W3.1 | TODO |
| W3.3 | Validation pass: each compiled check must execute against a skeleton workspace | `orchestrator/constitution.py` | NEW | W3.2 | TODO |
| W3.4 | Enforcement + reporting in delivery gate per rule id; mark constitution tests immutable | `delivery_gate.py`, `constitution.py` | SHARED | W3.2 | TODO |
| W3.5t | Tests: rule→pytest; non-compilable demoted; fix_test refused on constitution tests; immutable survives amendment | `tests/test_constitution.py` (NEW) | NEW | W3.1–W3.4 | TODO |

**Acceptance:** ☐ rules compile to executed checks ☐ advisory fallback ☐ enforced every round ☐ immutable respected by W2/W5

---

## Wave 4 — Tier routing + cost ledger  ·  status: TODO
Deps: **W1** (down-tiering safe only under the ladder). Phase A same-harness; Phase B registry is separate.

| ID | Task | Files | Isolation | Deps | Status |
|---|---|---|---|---|---|
| W4.1 | Role→tier→model config + persona→tier map + `model_for_role`; boss-never-codes guard | `config.py` | SHARED | — | TODO |
| W4.2 | Route at chokepoint: `chosen = _FORCE_MODEL > model arg > model_for_role(role,phase)` | `pipeline.py` | SHARED | W4.1, W1.2 | TODO |
| W4.3 | Per-tier cost ledger on `Usage` + zero-cost estimation from `PRICE_<TIER>_*`; counterfactual at DONE | `models.py`, `pipeline.py`, `config.py` | SHARED | W4.1, W0.3 | TODO |
| W4.4 | Frontend: tier breakdown + counterfactual in usage panel | `frontend/src/components/RunPanel.tsx`, `frontend/src/i18n/messages/` | SHARED(fe) | W4.3 | TODO |
| W4.5t | Tests: role→model matrix; boss-in-build guard; ladder precedence; ledger + zero-cost estimate | `tests/test_tier_routing.py` (NEW) | NEW | W4.1–W4.3 | TODO |
| W4.6 | Phase B (DEFERRED): cross-provider runner registry in `_UsageTracker` honoring `RunnerCapabilities` | `pipeline.py`, `runner.py` | SHARED | W4.5t | TODO |

**Acceptance:** ☐ dev→worker, critic→checker, arbiter→boss ☐ boss never codes in build ☐ ledger + counterfactual shown

---

## Wave 5 — Hardening  ·  status: TODO
Deps as noted per task.

| ID | Task | Files | Isolation | Deps | Status |
|---|---|---|---|---|---|
| W5.1 | Human-gated design amendment: `amendment.py` proposal + independent weakening-check + approval-gate queue | `orchestrator/amendment.py` (NEW), `pipeline.py`, `config.py` | NEW+SHARED | W1.3, W2.2, W3.4 | TODO |
| W5.2 | Model scorecard from telemetry (workers): green@1, attempts, escalation freq, cost/green; optional probation | `orchestrator/scorecard.py` (extend W0.2) | NEW | W0.2 | TODO |
| W5.3 | Checker-independence: include story `git diff` in `critic_review`; assert maker text never sole critic input | `prompts.py`, `pipeline.py`, tests | SHARED | — | TODO |
| W5.5 | Judge-score calibration: correlate judge scores vs downstream outcomes from JSONL | `orchestrator/scorecard.py` | NEW | W0.2 | TODO |
| W5.6 | Arbitration→lessons: feed fix_test/tampered/skeleton verdicts into `lessons.py`/retro | `orchestrator/lessons.py`, `pipeline.py` | SHARED | W2.2, W0.5-HOOK | TODO |
| W5.4 | Cross-family checking (DEFERRED): checker family ≠ worker family | `pipeline.py`, `config.py` | SHARED | W4.6 | TODO |
| W5.7 | Product-specific (DEFERRED): protected passages (as constitution rule) + persona testing | `constitution.py`, `runtime_acceptance.py` | mixed | W3.2 | TODO |
| W5t | Tests for amendment (human-gated, weakening rejected, depth bound), scorecard, independence | `tests/test_amendment.py`, extend `test_scorecard.py` | NEW | above | TODO |

**Acceptance:** ☐ amendment human-gated + weakening rejected ☐ scorecards for workers & checkers ☐ critic sees git diff

---

## Finalization  ·  status: TODO
| ID | Task | Deps | Status |
|---|---|---|---|
| FIN.1 | Full `uv run pytest` green (backend) + frontend tests where touched | all waves | TODO |
| FIN.2 | Update VERIFIED_SWARM_UPGRADE.md: mark shipped, note deltas vs current impl | all waves | TODO |
| FIN.3 | Update backend `.env.example` / docs with all new flags | all waves | TODO |

---

## Execution notes (living)
- 2026-07-08: branch created, decomposition written. Starting Wave 0 (all SHARED, sequential).
- Parallelization policy: fan out `NEW`-isolation tasks to subagents; keep all `SHARED` edits single-writer on this branch. Worktrees reserved for any fully self-contained `NEW` cluster that also needs its own test run.
