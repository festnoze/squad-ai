# Verified Swarm Upgrade — Autospec (v2)

**Source:** *"Claude Fable 5 Bossed 20 Cheap AI Agents. The Whole Site Cost $8."* — Nate B Jones (AI News & Strategy Daily), 19:17.
A frontier "boss" orchestrated ~20 cheap workers across 4 model families to rebuild a website in ~1.5h for ~$8 (vs. $85–105 frontier-only). Thesis: **hallucination isn't solved, it's structurally engineered out** — every task ships with an *executed* check, and even the checker and the boss get checked.

**v2 note.** This plan was rewritten after a critical review of v1 against the actual codebase. v1 ordered work by cost ROI (tier routing first); v2 orders it by **reliability and output quality**, because:
1. Autospec already has more verification machinery than the video — much of it **switched off by default** (`REFINE`, `MUTATION`, `COVERAGE`, `RUNTIME_ACCEPTANCE`, `EVALUATOR`, `SECURITY_REVIEW`, `DOD_STRICT_CRITERIA`, `REVIEW_PLAN`). The cheapest reliability win is zero new code.
2. Cheaper workers fail more; tier routing **without** an escalation ladder is a reliability *regression*. They must ship together, ladder first.
3. The video's "who checks the checker" (catch #4) maps in Autospec not to critic/judge disputes (off by default, small surface) but to the **QA agent writing a wrong test**: pytest's verdict is a fact, but the *test content* is a judgment artifact authored by an agent. Today a wrong test burns all dev attempts, triggers a pointless split, and fails the story. That is the highest-value arbitration target.
4. Letting the system rewrite acceptance criteria when it can't meet them is the most dangerous feature in v1 — it can legalize failure. In v2, design amendment is **human-gated by default**.

*(v2.1: adds Wave 0.5 — structural anti-cheating guards and harness hardening, the analog of the video's catch #2 "the worker that cheated" — plus AC↔test traceability (T2.0), judge calibration (T5.6) and arbitration→lessons feedback (T5.7).)*

---

## ✅ Implementation status (SHIPPED on branch `verified-swarm-upgrade`)

All six waves are implemented behind flags (default OFF ⇒ byte-identical legacy behavior), unit- and integration-tested, and committed. Per-task detail + the conflict/dependency map live in [todo_tasks.md](todo_tasks.md).

| Wave | Shipped | Key modules / hooks | Commit |
|---|---|---|---|
| 0 | ✅ | `PRESET=verified`, model-field + context telemetry, `scorecard.py` KPIs | `9693a6f` |
| 0.5 | ✅ | `signatures.py`, `guards.py`, `schema.py`; dev-loop guard hook + flaky rerun | `7c22fed`, `d06489c` |
| 1 | ✅ | `recovery.py` state machine + `_FORCE_MODEL` escalation ladder | `990b8ec` |
| 2 | ✅ | `traceability.py` / `classifier.py` / `arbitration.py`; `_amaybe_arbitrate_wrong_test` | `c167fa3`, `707ac7e` |
| 3 | ✅ | `constitution.py` compiler → `tests/constitution/`; `_amaybe_build_constitution` | `88ec3b8` |
| 4 | ✅ | `PERSONA_TIERS` + `model_for_role`; per-tier ledger + counterfactual | `09a52d3` |
| 5 | ✅ | `amendment.py` (human-gated) + scorecard/lessons/critic-independence | `c78e14e` |

**Deferred (documented in [todo_tasks.md](todo_tasks.md), not blocking):** streams-path guard/arbitration wiring (the streams path already has `_aenforce_file_scope`), golden-transcript CI harness (W0.5-T11), run-against-skeleton constitution validation (T3.3), frontend tier panel (W4.4), cross-provider runner registry + cross-family checking (W4.6/W5.4), judge-score calibration (W5.5, needs structured judge events), protected passages / persona testing (W5.7). W0.6 baseline needs a live agent run.

**Test footprint:** ~130 new tests across `test_scorecard/guards/schema/signatures/guards_integration/recovery/traceability/classifier/arbitration/arbitration_integration/constitution/constitution_integration/tier_routing/amendment/wave5`; full backend suite green. Every new env flag is listed in the per-wave **Config additions** table below; they are also written into `backend/.env.example` §9 for operator convenience (that file is git-ignored by the repo's `*.env*` rule, so it is not committed).

---

## 0. Current-state grounding (verified against code)

| Video pattern | Status in Autospec | Where |
|---|---|---|
| Executed checks per task (ignore self-report) | ✅ **Strong** | `_arun_pytest`, `runtime_acceptance.py`, smoke-run, coverage, `mutation.py`, `delivery_gate.py`, `post_merge_canary` |
| Verify → fail → feedback → retry | ✅ **Strong** | `refine.py::arefine` / `arefine_critic_first` (accept-gated, rollback), `dev_max_attempts` loop |
| Checker independence (checker reads reality, not the worker's report) | ✅ Mostly | `_arefine_code` (pipeline.py:2525) runs the critic with `cwd=ws` on the *files*, not the dev's narrative; `accept` = real pytest. Strengthen in W5 |
| Adaptive recovery on failure | ⚠️ Partial | `_amaybe_split_on_failure` (pipeline.py:3509) — splits scope only; no escalate-model, no wrong-test path, no design amendment |
| Per-phase model routing | ⚠️ Partial | `Settings.phase_models` + `model_for_phase` (config.py:574) resolved at the single chokepoint `_UsageTracker.arun` (pipeline.py:279) |
| Cost ledger | ⚠️ Partial | `Usage` accrual (pipeline.py:302–315); `AgentResult.cost_usd`; `*_price_in/out` settings. No per-tier breakdown; BuildMonitor `agent_call` lacks the **model** field |
| Boss/worker cost tiers | ❌ Absent | — (and note: `Pipeline.__init__(state, runner)` binds ONE runner — cross-provider tiers need a runner registry; within-Claude-family tiers are a `--model` switch) |
| Wrong-test arbitration ("who checks the checker") | ❌ Absent | a story failing on a bad QA test has no recourse |
| Model escalation on retry | ❌ Absent | retries reuse the same model |
| Design/spec amendment on recurring failure | ❌ Absent | split only |
| Project-wide constitution | ⚠️ Partial | per-story AC + Gherkin; no global, executable standard |
| Model audition | ❌ Absent | — v2 replaces synthetic auditions with a **telemetry scorecard** (BuildMonitor already logs every call/test) |
| Protected passages / persona testing | ❌ Absent | product-specific, deferred |

**Architecture recap.** Phases SPEC → ANALYZE → PLAN → (ARCHITECT) → BUILD → DONE. One runner per pipeline (`ClaudeCliRunner` = `claude -p --output-format json --model <id>`, `CodexCliRunner`, LangChain providers). **Every** agent call funnels through `_UsageTracker.arun` (pipeline.py:268), which already knows the persona role (line 271), resolves the model (line 279), accrues `Usage`, records the `AgentInteraction`, and feeds `BuildMonitor`. All new routing/telemetry hooks live there.

---

## 1. Design principles (invariants)

1. **Executed truth is non-negotiable; judgment artifacts are contestable.** Pytest/compile/smoke/coverage *verdicts* are facts — never disputable, never amendable. But tests, acceptance criteria, and critic opinions are *authored judgments* — each must have a contestation path that routes to a higher-tier ruling grounded in the spec.
2. **One recovery policy.** All failure handling (retry, escalate, arbitrate, split, amend) runs through a single explicit state machine with logged transitions — never ad-hoc interleaving of competing mechanisms.
3. **Cheap-first, escalate on earned failure.** Frontier tokens are spent only where a task proves it needs them. Routing down-tier is only allowed once the escalation ladder exists.
4. **The system may propose spec changes; only a human (or an explicit opt-in) approves them.** Amendment ≠ self-serving spec erosion.
5. **Everything new is flag-gated, default OFF**, mirroring the existing `*_enabled` convention. All flags off ⇒ byte-identical legacy behavior.
6. **Every routing/escalation/arbitration decision is logged** (`AgentInteraction` + BuildMonitor event) with its reason.
7. **Prefer enabling/hardening existing gates over building parallel new ones.**

---

## Wave 0 — "Verified-swarm" preset + baseline measurement (zero new machinery)

**Outcome:** the existing verification gauntlet turned ON as a named profile, plus the metrics to judge every later wave. Nothing in W1+ is justified without this baseline.

- **T0.1 — Preset profile.** Add a `verified` entry to `orchestrator/profiles.py` (or an env preset in `config.py`) that enables: `REFINE`, `REVIEW_PLAN`, `RUNTIME_ACCEPTANCE`, `COVERAGE` (+ modest `COVERAGE_GATE`), `MUTATION` (bounded `MUTATION_MAX`), `DOD_STRICT_CRITERIA`, `EVALUATOR`, `SECURITY_REVIEW`. Document the token-cost expectation honestly.
- **T0.2 — Reliability KPIs.** Small analyzer over `build-monitor.jsonl` (script or `orchestrator/scorecard.py`, shared with W5): per run — stories green on attempt 1 / after retries / failed; attempts per story; splits triggered; refine rounds & scores; cost per green story; wall-clock. This is the before/after yardstick for every subsequent wave.
- **T0.3 — Record the model per call.** Add `model=<resolved id>` to `BuildMonitor.agent_call(...)` (build_monitor.py:43) and to `AgentInteraction` — one field each, required by the ladder (W1), the scorecard (W5), and honest cost attribution (W4). Do it now while touching the chokepoint is cheap.
- **T0.4 — Run one real project** under the preset; keep the JSONL as the reference baseline.

**Effort:** S. **Risk:** none (flags exist; T0.3 is additive).

---

## Wave 0.5 — Anti-cheating guards & harness hardening

**Outcome:** the video's catch #2 ("the worker that cheated" — invisible paragraph, empty element) made structurally impossible in Autospec's terms, and the plumbing the later waves depend on made trustworthy. All checks here are **small, deterministic, and cheap**. They come *before* W1 because the recovery machine and arbitration assume failure signals are honest and clean — garbage signatures in, garbage escalations out.

### Anti-cheating (structural — a cut corner must not survive its check)
- **T0.5 — Test-tampering guard (`TEST_TAMPER_GUARD`, default off).** The most direct cheat available to a dev agent today: *edit the QA tests until they pass*. After each dev attempt, `git diff --name-only` against the story's QA-authored test files; any modification — outside an explicit W2 `fix_test` ruling — reverts the test files and records the attempt as `tampered` (a first-class failure signature for W1's history). Hook: the dev loop, immediately before `_arun_pytest`. Tests: dev edit of a QA test ⇒ reverted + flagged; a `fix_test`-sanctioned edit passes untouched.
- **T0.6 — Scope guard (`SCOPE_GUARD`, off; modes `warn|strict`).** `independence.py` already computes per-item file claims — but only *before* the build, for scheduling. Enforce them *after*: a worker whose diff touches files outside its declared claims is flagged (`warn`) or reverted (`strict`). Catches "cosmetically fine" shortcuts that break sibling streams *before* the merge, complementing `post_merge_canary`.
- **T0.7 — Skeleton-implementation detector (`SKELETON_GUARD`, off).** Deterministic AST/grep pass over the story's new code: `pass`-only bodies, return values hardcoded to test literals, `pytest.skip`/`xfail` insertions. Flags as a failure signature; mutation testing (W0 preset) remains the deep backstop for subtler gutting.

### Harness hardening (the checks themselves must be reliable)
- **T0.8 — Flaky-check quarantine (`FLAKY_RERUN`, off).** A checker that lies intermittently is worse than none. A red test is rerun once before it becomes a failure signature: flake ⇒ not counted (W1 must never escalate a model over a flake); repeated flip-floppers are quarantined and reported to the operator. **Hard prerequisite for W1.**
- **T0.9 — Schema-validated decision outputs.** `extract_json` (runner.py:436) tolerantly scavenges the first JSON object from prose — a misparse silently becomes a wrong decision (a judge score, an independence verdict). For *decision-bearing* calls, validate against a per-call schema and retry once with the validation error appended. Build now, apply to the existing judge/independence calls; the classifier (W1) and arbiter (W2) adopt it from day one.
- **T0.10 — Hallucinated-import guard (`IMPORT_GUARD`, off).** Post-build deterministic check: every import in generated code resolves to the dependency manifest or the stdlib. Catches hallucinated packages statically — before `uv run` does at runtime, and closing the slopsquatting supply-chain angle the S1 security review doesn't check statically.
- **T0.11 — Golden-transcript regression suite (CI infra, no flag).** Prompts are load-bearing code with zero tests: a prompt tweak can silently degrade every downstream build. Record `fake_agents`/FakeRunner scenario transcripts as goldens in CI so any prompt or loop change fails visibly. This protects **the waves themselves** — W1–W5 all modify prompts and loop logic.
- **T0.12 — Context-budget telemetry (no flag, rides T0.3).** Log prompt size per call in `_UsageTracker`/BuildMonitor; warn when approaching the model's context limit. Silent truncation is a classic source of "mysteriously dumb" agent behavior that would otherwise waste W1 ladder rungs on an unwinnable prompt.

**Effort:** S each. **Risk:** low — all deterministic and additive; `warn` modes allow observing before enforcing.

---

## Wave 1 — Unified recovery state machine + model-escalation ladder

**Outcome:** a red task climbs a *defined* recovery path instead of burning identical retries: **retry(same rung) → escalate rung → classify root cause → split | arbitrate | amend-proposal → fail-partial**. Direct red→green win; prerequisite for safe down-tiering (W4).

### T1.1 — Recovery policy module
- **New file:** `backend/autospec/orchestrator/recovery.py` — a pure, unit-testable state machine: `next_action(history: TaskFailureHistory) -> RecoveryAction` where actions = `RETRY | ESCALATE(model) | CLASSIFY | SPLIT | ARBITRATE | AMEND_PROPOSAL | FAIL`.
- `TaskFailureHistory` carries per-attempt: model used, normalized failure signatures (test node id + exception type via `toolchain.parse_results` / `pytest_report.py`), infra-vs-dev flag (the existing `infra_max_retries` distinction stays upstream of this machine). Signatures are **flake-filtered (T0.8)** and include the W0.5 guard verdicts (`tampered`, `out_of_scope`, `skeleton`) — cheating is a failure class the machine reacts to, not a bypass.
- **Refactor, don't duplicate:** the existing decision points in the dev loop (attempts at pipeline.py:3095, 4083–4161; `_amaybe_split_on_failure` call sites) delegate to `recovery.next_action`. `SPLIT` keeps its exact current semantics (`split_max_depth` etc.) — with all new flags off, the machine must reproduce today's retry→split→fail behavior **byte-identically** (regression-tested).
- Every transition emits a BuildMonitor event: `{"kind":"recovery","action":...,"reason":...,"signatures":[...]}`.

### T1.2 — Model-escalation ladder (`ESCALATE_ON_RETRY`, default off)
- **Config:** `model_ladder: list[str]` from `MODEL_LADDER` (comma-separated, cost-ascending; e.g. `claude-haiku-4-5-20251001,claude-sonnet-4-6,claude-opus-4-8`). Phase A is **same-harness only** (Claude-family via the CLI's `--model`) — no runner changes. Cross-provider rungs arrive with W4b.
- **Mechanism:** attempt *n* runs on rung *n* (clamped to the top). Thread the forced model via a `_FORCE_MODEL` contextvar (mirroring `_BUILD_ITEM`, pipeline.py:238) read in `_UsageTracker.arun` with precedence: explicit `model` arg > `_FORCE_MODEL` > router. Escalation applies to the **dev call of that attempt** (and its QA-fix companion), not globally.
- Fresh rung ⇒ fresh session (no `session_id` carry-over): a stronger model gets fresh eyes plus the structured failure feedback the loop already builds.
- Ladder exhausted ⇒ `CLASSIFY` (T1.3), not immediate split. Each escalation logged: "task X promoted haiku→sonnet (signature S recurring)".

### T1.3 — Root-cause classification (replaces v1's brittle same-signature trigger)
- When the ladder is exhausted and the task is still red, one **boss-tier** call classifies the failure history (signatures, diffs tried, test bodies, AC): verdict ∈ `too_big` → `SPLIT` | `wrong_test` → `ARBITRATE` (W2) | `spec_contradiction` → `AMEND_PROPOSAL` (W5) | `genuinely_hard` → `FAIL` (partial delivery as today).
- Rationale: "same signature ≥K times" (v1) never fires when attempts fail on *different* tests though the task is equally stuck; classification covers all stuck shapes with one cheap call at a bounded point.
- New persona `classifier` in `personas.py` (registered in `FALLBACK_PERSONAS` so `_persona_role` labels it); prompt in `agents/prompts.py`.

### T1.4 — Tests
- `recovery.py` pure-unit: full transition matrix; flags-off ⇒ legacy-equivalent sequence.
- FakeRunner integration: red on rung 1 / green on rung 2 ⇒ assert `FakeRunner.calls[*]["model"]` climbed; ladder exhausted ⇒ classifier consulted; `infra` errors don't consume rungs.

**Effort:** M. **Risk:** medium — the refactor touches the dev loop's hot path; the byte-identical-when-off regression suite is the safety net.

---

## Wave 2 — Test-vs-implementation arbitration (the real "who checks the checker")

**Outcome:** a story can no longer be killed by a wrong test. When classification says `wrong_test`, a boss-tier arbiter rules with the AC/Gherkin as the constitution — the video's catch #4, aimed at Autospec's actual failure mode.

### T2.0 — AC↔test traceability matrix (`AC_TRACEABILITY`, default off)
- The video's core claim made literal: *34 tasks, every one checked*. Autospec has ACs (S2), Gherkin (S3) and tests — but no machine link between them. Require QA tests to carry the AC id they verify (docstring marker, e.g. `AC: US-3.2`); the delivery gate then verifies **every AC has ≥1 executed test** and flags **orphan tests** (asserting behavior no AC asked for — the origin of most wrong tests).
- Changes: QA prompt (`agents/prompts.py`) + a marker parser + `delivery_gate.py` check. Turns `DOD_STRICT_CRITERIA` from declarative into executed.
- Direct payoff for arbitration below: the arbiter sees exactly which AC a disputed test claims to verify — an orphan test failing a story is near-automatic `fix_test` evidence.

### T2.1 — Arbitration module (`DISPUTE_ESCALATION`, default off)
- **New file:** `backend/autospec/orchestrator/arbitration.py` — `async def aarbitrate_test(runner, *, story, test_source, failure_output, impl_diff, criteria, cwd, emit) -> Ruling` with `Ruling = {verdict: "fix_impl" | "fix_test" | "spec_contradiction", reason: str, instructions: str}`.
- Boss-tier persona `arbiter` (added to `FALLBACK_PERSONAS`). The prompt's ground truth is the story's **acceptance criteria + Gherkin** (delivery_gate already extracts these); the arbiter reads the actual test file and run output — executed evidence, not narratives.
- **No worker-rebuttal step** (v1 had one — dropped): arbitration triggers *automatically* from classification (T1.3). An extra self-advocacy call per failure adds cost and invites motivated arguing; the failure history already contains the worker's case.

### T2.2 — Rulings wired into the loop
- `fix_impl` → arbiter's instructions become the guidance of one final dev attempt (top rung) — the "here is precisely what is wrong" feedback the video shows.
- `fix_test` → a **checker-tier** QA-fix call rewrites the offending test to match the AC (never deleting coverage: the arbiter's instructions must state what the test *should* assert); then rerun the suite. The corrected checker is the video's catch #4 outcome. One `fix_test` per story per iteration (`arbitration_max` guard) — a loop of test rewrites would be checker erosion.
- `spec_contradiction` → hand off to amendment (W5) as a human-pending proposal; the story keeps its FAILED/partial-delivery path meanwhile.
- **Hard rule (principle 1):** arbitration is only reachable through classification after the ladder — never invoked because a worker "wants" it, and never on infra errors.

### T2.3 — Surface it
- Log ruling + reason as `AgentInteraction` on the story + BuildMonitor `{"kind":"arbitration",...}`; show in the item activity view (`frontend/src/components/Activity.tsx`) — "failures investigated in both directions."

### T2.4 — Tests
- FakeRunner: (a) wrong test (asserts behavior absent from AC) ⇒ classifier→arbiter ⇒ `fix_test` ⇒ QA-fix ⇒ green; (b) `fix_impl` ⇒ one guided top-rung attempt; (c) second `fix_test` on the same story is refused; (d) a plain flaky infra failure never reaches arbitration.

**Effort:** M. **Risk:** medium — `fix_test` weakening real coverage is the danger; mitigated by AC-grounding, the arbiter's must-assert instructions, and `arbitration_max`. Mutation testing (Q1, on in the W0 preset) is the independent backstop that detects gutted tests.

---

## Wave 3 — Constitution compiler (global standard as *executed* checks)

**Outcome:** a project-wide "done-right" standard defined once after SPEC and enforced on every round — but only in the video's sense: **compiled to executable checks**, not prose a gate can't run.

### T3.1 — Constitution phase (`CONSTITUTION`, default off)
- **New file:** `backend/autospec/orchestrator/constitution.py`; hook between SPEC and PLAN. A boss-tier call derives N project-wide rules from the brief (security, perf budget, a11y, API conventions, domain invariants), each declared as `{id, statement, kind: test|command|advisory, immutable: bool}`.

### T3.2 — The compiler (the part that makes it real)
- Each rule **must compile at creation** into:
  - `test` → a pytest file seeded under `tests/constitution/` in the workspace — rides the existing deterministic gate, per-story worktrees, and `post_merge_canary` with **zero new enforcement machinery**; or
  - `command` → an entry the delivery gate executes (like the existing pip-audit/npm-audit pattern in the security review);
  - anything that can't compile is demoted to `advisory` — injected into dev/QA prompts (alongside `build_guidance`/lessons) and into refine `criteria`, but never "enforced" as decoration.
- A checker-tier validation pass runs each compiled check against an empty/skeleton workspace to ensure it *executes* (a constitution test that errors out is itself a wrong checker).

### T3.3 — Interplay rules
- Compiled constitution tests are **immutable for W2 arbitration** (`fix_test` may never target `tests/constitution/`) and immutable-flagged rules are untouchable by W5 amendment. The constitution is the floor under both contestation mechanisms.
- Delivery gate (`evaluate_definition_of_done`) reports constitution compliance per rule id.

### T3.4 — Tests
- Rule→pytest compilation; non-compilable rule demoted to advisory; `fix_test` refused on constitution tests; immutable rule survives an amendment proposal.

**Effort:** M. **Risk:** medium — over-eager generated rules could block everything; start with a low N (5–8) and the advisory demotion valve.

---

## Wave 4 — Tier routing + per-tier cost ledger (now safe under the ladder)

**Outcome:** the video's headline economics — boss plans/reviews/arbitrates, cheap workers code, mid checkers verify — adopted **after** W1 exists so cheap-worker failures escalate instead of failing stories.

### T4.1 — Role→tier→model config (`ROLE_ROUTING`, default off)
- `config.py`: `model_tiers` from `MODEL_BOSS` / `MODEL_WORKER` / `MODEL_CHECKER` (fallback: `claude_model`); persona→tier map as a module constant:
  - `boss`: pm, po, sm, analyst, architect, **arbiter**, **classifier**, retro
  - `worker`: dev, dev-frontend
  - `checker`: qa, **critic**, **judge**, evaluator, security-reviewer, independence-judge — *(v1 correction: critic/judge ran per-round-per-item; routing them to boss multiplies frontier spend for no reliability gain. Only arbitration/classification — rare, bounded, high-stakes — earns boss pricing.)*
- `Settings.model_for_role(role, phase)`: tier model if enabled & mapped, else `model_for_phase(phase)`.
- **Phase A constraint:** all tiers same-harness (Claude family). Guard: in BUILD, a dev call resolving to the boss model logs a warning and falls back to worker tier ("boss never codes", enforced in `model_for_role`, not sprinkled in the tracker).

### T4.2 — Route at the chokepoint
- `_UsageTracker.arun` line 279: `chosen = model or settings.model_for_role(role, phase)` — with `_FORCE_MODEL` (ladder) taking precedence per T1.2. One line; the `role` local already exists.

### T4.3 — Per-tier cost ledger + counterfactual
- Extend `Usage` (models.py) with per-tier buckets; attribute deltas in `_UsageTracker.arun` (tier from role). When the runner returns `cost_usd == 0`, estimate from `PRICE_<TIER>_{IN,OUT}` (reuse `_env_float`, mirroring `*_price_in/out`).
- At DONE emit the counterfactual: actual cost vs. `total_tokens × boss price` — the "$8 vs. $100" line. Surface tier breakdown + counterfactual in the usage panel (`frontend/src/components/RunPanel.tsx`; i18n in `frontend/src/i18n/messages/`).

### T4.4 — Phase B: cross-provider runner registry (separate task, do not bundle)
- `Pipeline` binds one runner; true multi-family tiers (cheap non-Claude workers, cross-family checkers) need per-call runner selection in `_UsageTracker` keyed by tier → (provider, model), honoring `RunnerCapabilities` (`reliable_for_build` — LangChain chat runners must not take BUILD work). This also unlocks **cross-family checking** (W5). Scope it only after Phase A metrics prove the routing pays.

### T4.5 — Tests
- `model_for_role` matrix (flag off / tier unset / boss-in-build guard); FakeRunner asserts dev→worker-model, critic→checker-model, arbiter→boss-model; ladder precedence over routing; ledger attribution incl. zero-cost estimation.

**Effort:** S–M (Phase A). **Risk:** low behind the flag — and reliability-neutral now that failures escalate (W1) and wrong tests get arbitrated (W2).

---

## Wave 5 — Hardening: amendment (human-gated), scorecard, independence, cross-family

### T5.1 — Design amendment as human-pending proposals (`DESIGN_AMENDMENT`, default off)
- Trigger only from classification (`spec_contradiction`, T1.3) or arbitration (`spec_contradiction`, T2.2) — never directly from a red test.
- **New file:** `orchestrator/amendment.py`. Boss-tier call drafts a minimal AC/Gherkin/architecture amendment: `{target, before, after (diff), rationale}`. An **independent boss-tier check** answers one question — "does this weaken the requirement?" — and rejects if yes.
- Surviving proposals are **queued for human approval** through the existing `approval_gates_enabled` machinery (pipeline pauses exactly as the post-plan gate does). `AMENDMENT_AUTO=1` is a separate, explicit opt-in for unattended runs; `amendment_max_depth` (default 1) bounds re-derivation either way. Approved ⇒ artifact patched, story re-derived, attempts reset once; logged "design changed to prevent error X".
- Immutable constitution rules and protected passages are non-targets.

### T5.2 — Model scorecard from live telemetry (replaces v1's synthetic auditions)
- The factory already generates *real* per-model evidence — BuildMonitor logs every call and test; T0.3 adds the model id. `orchestrator/scorecard.py` aggregates per model: green-on-first-attempt rate, attempts-to-green, escalation frequency, arbitration outcomes, cost per green story.
- Used two ways: operator-facing report (which cheap model actually earns its place — a continuous audition on real work, strictly better than a one-shot tryout task), and input for ladder/tier ordering. Optionally: a new model enters the worker tier with a probation cap (first N tasks watched; auto-demoted below a floor) — auditioning on *real* tasks under the ladder's safety net.

### T5.3 — Checker-independence strengthening
- Verified: the code critic already reviews workspace files (`cwd=ws`), not the dev's report. Strengthen: include the **actual `git diff` of the story's commits** in the critic prompt (`prompts.critic_review`) so review targets exactly what changed rather than relying on the critic's own directory walk; assert in tests that the maker's chat text is never the sole critic input for code artifacts.

### T5.4 — Cross-family checking (needs T4.4)
- Same-family checker ≈ self-grading with shared blind spots (why the video ran 4 families). Once the runner registry exists: prefer a checker/arbiter family different from the worker's (e.g. Claude workers ⇄ Codex-side checker, or vice versa), flag-gated per tier.

### T5.5 — Judge-score calibration (rides the T0.2/T5.2 analyzer)
- The judge emits 0–100 against `refine_quality_threshold=80` — but is 80 *meaningful*? Correlate scores with downstream reality from `build-monitor.jsonl`: did stories scored 90 fail runtime acceptance more often than ones scored 82? A checker whose scores don't predict outcomes is paid noise — recalibrate the threshold, or replace the judge prompt and re-measure. Scorecards apply to **checkers, not just workers**.

### T5.6 — Arbitration→lessons feedback
- Every `fix_test` ruling (W2) is evidence of *how* the QA agent writes wrong tests; every `tampered`/`skeleton` flag (W0.5) is evidence of how dev agents cut corners. Feed both into the existing `lessons.py`/retro (E7) pipeline so QA/dev prompts accumulate targeted lessons ("don't assert behaviors absent from the AC", "never modify test files"). The factory learns from its own disputes — the machinery already exists.

### T5.7 — Product-specific (as needed): protected passages & persona testing
- `PROTECTED_PASSAGES`: manifest of verbatim blocks (hashes) checked character-for-character every build (the video's 171-passage check) — as a compiled constitution rule (W3), i.e. free enforcement. For brownfield/content builds.
- `PERSONA_TESTS`: end-user personas (distinct from internal roles in `personas.py`) whose scenarios run via `runtime_acceptance.py`/Playwright (`UI_TESTS`) and can outrank other requirements. For UI products.

**Effort:** S–M each. **Risk:** T5.1 stays safe by construction (human gate + weakening check + depth bound).

---

## Config additions (all default OFF; flags off ⇒ byte-identical legacy behavior)

| Env var | Setting | Wave | Purpose |
|---|---|---|---|
| *(preset)* | `verified` profile | 0 | Enable the existing verification gauntlet |
| `TEST_TAMPER_GUARD` | `test_tamper_guard` | 0.5 | Revert dev edits to QA-authored tests |
| `SCOPE_GUARD` (`warn`\|`strict`) | `scope_guard` | 0.5 | Enforce declared file claims post-hoc |
| `SKELETON_GUARD` | `skeleton_guard` | 0.5 | Detect pass-only / hardcoded / skipped implementations |
| `FLAKY_RERUN` | `flaky_rerun_enabled` | 0.5 | Rerun red tests once; quarantine flip-floppers |
| `IMPORT_GUARD` | `import_guard` | 0.5 | Imports must resolve to manifest/stdlib |
| *(no flag)* | schema validation, goldens, context telemetry | 0.5 | Harness hardening (internal) |
| `ESCALATE_ON_RETRY` / `MODEL_LADDER` | `escalate_on_retry_enabled` / `model_ladder` | 1 | Climb models on retry (same-harness) |
| `AC_TRACEABILITY` | `ac_traceability_enabled` | 2 | Every AC ⇒ ≥1 executed test; orphan tests flagged |
| `DISPUTE_ESCALATION` / `ARBITRATION_MAX` | `dispute_escalation_enabled` / `arbitration_max` | 2 | Wrong-test arbitration, bounded |
| `CONSTITUTION` | `constitution_enabled` | 3 | Global standard compiled to executed checks |
| `ROLE_ROUTING` + `MODEL_{BOSS,WORKER,CHECKER}` + `PRICE_<TIER>_{IN,OUT}` | `role_routing_enabled` / `model_tiers` / `tier_price_*` | 4 | Boss/worker/checker tiers + honest ledger |
| `DESIGN_AMENDMENT` / `AMENDMENT_AUTO` / `AMENDMENT_MAX_DEPTH` | `design_amendment_enabled` / `amendment_auto` / `amendment_max_depth` | 5 | Human-gated spec amendment |
| `CROSS_FAMILY_CHECKERS` | `cross_family_checkers` | 5 | Checker family ≠ worker family (needs runner registry) |
| `PROTECTED_PASSAGES` / `PERSONA_TESTS` | — | 5 | Product-specific gates |

---

## Sequencing, dependencies & measurement

```
W0 preset+KPIs+model-field ──► baseline numbers
        │
W0.5 anti-cheating guards + harness hardening ──► honest, flake-free failure signals
        │
W1 recovery machine + ladder ──► red→green ↑ (measure vs. baseline)
        │
W2 traceability + wrong-test arbitration ──► stories-failed-on-bad-tests → ~0
        │
W3 constitution compiler ──► global-quality violations → executed reds
        │
W4a tier routing + ledger ──► cost/green-story ↓ at equal reliability
        │
W5 amendment · scorecards (workers+checkers) · lessons · independence · (W4b registry → cross-family)
```

- **Every wave is judged by the W0 KPIs**: green-on-first-attempt rate, attempts per green story, stories failed, cost per green story, wall-clock. A wave that doesn't move its metric gets reverted behind its flag, not accreted.
- W1 depends on W0.5 (T0.8 flake-filtering and T0.9 schema validation feed it clean, structured signals). W2 depends on W1 (classification is the only entry to arbitration) and is sharpened by T2.0 traceability. W4a depends on W1 (down-tiering is only safe under the ladder). W5.4 depends on W4b; W5.6 consumes W0.5/W2 verdicts.
- **Framing:** Autospec already built the expensive half — execution-based verification. v2 adds the three things the video shows and the code lacks: a *disciplined recovery ladder*, *contestable checkers grounded in the spec*, and *a global standard that compiles to executed checks* — then, and only then, the cost story.

---

## Key anchor points (verified against current code)

- Single chokepoint (route, role label, usage, interactions, monitor): `_UsageTracker.arun` — `backend/autospec/orchestrator/pipeline.py:268` (model at ~279, `role` at ~271, usage at 302–315); `_BUILD_ITEM` contextvar pattern at pipeline.py:238.
- Per-phase model config: `Settings.model_for_phase` — `backend/autospec/config.py:574`; `phase_models` at 159; price-setting pattern at 185–232.
- Runner honors explicit `model=`: `ClaudeCliRunner.arun` `runner.py:192`; `CodexCliRunner.arun` `runner.py:332`; Protocol `runner.py:163`; `RunnerCapabilities` `runner.py:147`; **one runner per pipeline** `pipeline.py:352`.
- Refine loop: `refine.py::arefine` (105) / `arefine_critic_first` (159); code-critic independence evidence: `_arefine_code` `pipeline.py:2525` (`cwd=ws`, pytest-gated `accept`, git rollback).
- Dev-attempt loop + recovery hook points: `dev_max_attempts` at `pipeline.py:2952, 3095, 3928, 4083–4161`; `_amaybe_split_on_failure` `pipeline.py:3509`; infra-vs-dev budget `config.py:540`.
- Failure signatures: `toolchain.parse_results`, `pytest_report.py`.
- Telemetry: `BuildMonitor.agent_call` `build_monitor.py:43` (**add `model` field — T0.3**); JSONL at `workspace/<project>/build-monitor.jsonl`; `AgentInteraction` store `interactions.py:44`.
- Human gates: `approval_gates_enabled` `config.py:429` (reuse for amendment approval).
- Delivery gate / DoD: `delivery_gate.py::evaluate_definition_of_done`.
- W0.5 hook points: file claims for the scope guard `orchestrator/independence.py`; lessons pipeline for T5.6 `orchestrator/lessons.py` + retro (E7); JSON scavenger to harden `runner.py::extract_json` (436); demo/CI harness for goldens `fake_agents` `config.py:261` + `FakeRunner` `runner.py:360`.
