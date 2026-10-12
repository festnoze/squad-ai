# Integration checkpoints — 12 October 2026

Factory supervisor tests only, in the managed integration worktree. No paid
model call, product repair, original campaign mutation or other-project cleanup.
Generated application probes, when applicable, remain in owned Linux Docker
NETNONE resources. XML and JSON are raw copies, not reconstructed summaries.

## Complete regression and timing replay

- `full-regression-third-snapshot.xml`: frozen source Git SHA
  `8dffd0e8cfb47324637ea3c3007e5561ac3bb587`, **2,583 PASS, 10 FAIL, 74 SKIP**,
  3,299.91 s. Nine failures are finite factory-test deadline overruns; one is
  genuinely wrong pytest collection root in an ancestor-configured repository.
  This is retained as a failed checkpoint, not labelled green.
- `global-failures-timing-replay-v1.xml`: **154 PASS**, 492.53 s, all four
  timeout-failing modules (`test_api`, `test_pipeline`, `test_split_on_failure`,
  `test_independence`). Only native Windows factory-fixture deadlines were
  enlarged, to finite 90 s where needed. Assertions, real Git execution,
  concurrency maxima, task statuses and product performance criteria are
  unchanged. This does not claim faster production orchestration.
- `git-latency-diagnostic.json`/`.xml`: nine successful real hermetic Git
  commands, 3.409748 s total; individual commands 0.309–0.574 s. These observations
  do not establish Git as the dominant cause of the fixture delay.
- `claims-root-counterreview-v2.xml`: **45 PASS**, 71.35 s; independent review
  confirmed serialization, sibling completion and child-failure assertions
  remain intact.
- The collection-root fix is separate commit `21dc8b50`: explicit disposable
  pytest `--rootdir=.` and target `.`. Integrity parsing is not weakened by
  accepting arbitrary node-ID suffixes. Teammate native evidence is retained
  separately under REM-05.

## Source review and publication lifecycle

- `root-publication-entropy-v1.xml`: retained **3 FAIL / 92 PASS**. Synthetic
  fixtures omitted their explicit security profile; this was corrected in the
  fixtures, not by bypassing the source-only admission rule.
- v2: **97 PASS**, 3.28 s; v3: **128 PASS / 3 explicit opt-in SKIP**, 3.87 s;
  v4: **136 PASS / 3 explicit opt-in SKIP**, 4.42 s. These are factory mechanics
  proofs, not acceptance of a generated support product. Native entropy and
  publication evidence is retained in its own task folders.
- Dedicated entropy R reviews full value propagation and exact CSPRNG binding;
  native X separately observes entropy arguments and the whole-cookie digest.
  Generic binding approval is not entropy approval. A cached old review is
  invalidated by protocol/engine hash, re-requested once per context and phase,
  and safely resumable without re-archiving every fresh response.
- Publication refuses stale qualification, preserves a previous running service
  on a failed update, cleans up only a newly owned runtime after late
  cancellation, recovers an active durable journal even if state flush was
  interrupted, and never resurrects intentionally stopped/destroyed resources.
- `source-plan-api-root.xml`: **68 PASS**, 0.90 s. A source-sealed lot limit is
  checked before persistence or provider/pipeline work; booleans, strings,
  floats and changed limits are refused. Generic four-lot and support seven-lot
  cases both pass; no support-specific hardcode in the API.
- `root-last-raccord-v2.xml`: **146 PASS**, 14.12 s, combined current source
  review/external handoff, publication recovery, delivery/quality review,
  API/plan limits and final admission modules. The first command used a
  nonexistent audit test filename and collected no tests; it is not a PASS
  checkpoint. The corrected explicit target list produced this XML.
- `owned-publication-parent-20261012.xml`: **18 PASS / 1 FAIL**, 75.46 s,
  including both real Docker tests PASS (baked image/persistence/process-death
  recovery and migration before an application refusing an empty DB). A Windows
  `WinError 5` in `atomic_json` failed a mocked fixture setup before its adversarial
  mutation. This failed checkpoint is retained; a bounded atomic-replace
  robustness fix and replay are required, not a retry labelled silently green.
- `owned-raccord-packages-v1.xml`: **68 PASS / 3 native opt-in SKIP**, 12.23 s.
  The root now selects external package or publication registries from the
  structured stack even when state flush never persisted an image/CID. No
  contract cleanup uses legacy names. Late package cancellation removes only
  a fresh-call alias receipt; a previously existing package is preserved.
  This unit replay does not replace the teammate's native package proof.

## Independent late counterexamples and corrected parent replay

- `owned-publication-parent-v2.xml`: **37 PASS**, 184.27 s. Actual Docker
  publication/migration/persistence and actual Windows file-handle contention;
  this resolves the retained atomic-replace failure, not the whole regression.
- `owned-lifecycle-independent-before.xml`: **9 FAIL**, 2.04 s. Independent
  offline ASGI/inert-thread counterexamples exposed contract DELETE entering
  legacy cleanup or ignoring a pre-flush journal, and publication cancellation
  releasing a still-live worker. No generated application ran on the host.
- `budget-cache-root-v1.xml`: **101 PASS / 2 FAIL**, 31.24 s. The remaining
  failures were a reviewed E2E mode not forwarded into its seal hash and an
  obsolete budget-message assertion. The E2E mode was fixed in coordinator;
  the budget message now explicitly requires attested reconciliation.
- v2: **113 PASS / 1 FAIL**, 15.18 s; an old recovery mock did not yet accept
  the newly forwarded cancellation event. It was corrected with an exact event
  identity assertion, not a permissive fallback in production.
- `owned-budget-cache-root-v3.xml`: **146 PASS**, 18.70 s. Final factory-only
  replay includes repeated cancellation with a blocked worker, fresh-call CID
  cleanup versus preserved reuse, startup recovery drainage, both journal types
  before project deletion, absent/claimed/corrupt/outage cases, unknown historic
  costs even with caps removed, exact reviewed E2E mode, and final-report cache
  invalidation for absent context, changed seals/engine/report bytes.
- Superseded reports are retained. Report reuse requires current source-review
  admission FIRST, exact factory `.py`/browser `.cjs` hashes, reviewed external
  configuration/seals and the exact serialized report SHA. A cache identity is
  not an X/R/V acceptance proof. Cost counters and known amounts are preserved;
  resume, feedback or a different cap cannot silently reconcile missing usage.
- Withdrawal intent is durable (`stopping`) before Docker mutation. A failed
  terminal flush cannot make startup recreate an intentionally withdrawn app.
  Native peer evidence and its failed fixture callback are kept under REM-01.

These are scoped mechanics and counterexample replays, not 57 product PASSes.
The corrected full regression and fresh REM-25 campaign are still required.

## Factory frontend

- `frontend-root-v4.xml`: actual locked Vitest **4.1.11**, **308 PASS**, 7.9475 s,
  after `npm ci --ignore-scripts` from the new lock (zero audit vulnerabilities).
  Actual `tsc -b` and Vite **6.4.4** build also succeeded, 1.34 s; the large-chunk
  warning remains a non-blocking factory-bundle diagnostic. Unit/build stdout
  was observed directly; no fabricated log file is supplied.
- The run link uses `127.0.0.1`, matching the publication registry's exact
  allowed loopback Origin. The allowlist is not broadened to hide the mismatch.

These late integration checks do not replace a complete regression on the
eventual final commit or the independent REM-25 campaign and its 57 verdicts.
