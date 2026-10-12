# Native quality collection raccord — checkpoint

2026-10-12. No provider/API/model call was made. This checkpoint consumes an
external sealed reviewed quality plan; it never prepares or approves a plan.

`collect_native_quality(state, contract, source_root, snapshot_hash,
supervisor_root, validator=None)` returns `OBTAINED`, `PARTIAL` or
`NOT_VERIFIED`, not requirement acceptance. It publishes obtained X observations
and exact proof indexes through `SupervisorEvidenceStore`. Failed suites,
coverage below threshold and failed browser assertions remain in their values.
The quality/final gates must independently evaluate those values and X/R/V.

Command receipts retain only `IsolatedSuiteResult.execution_receipt` actually
returned by the isolated runner, equal to its external `.execution.json`
sidecar. The wrapper binds these bytes to the overall snapshot and contract.
No likely argv, exit zero, missing coverage or missing clock is synthesized.
Tests and install durations come from separate monotonic execution clocks;
browser timing surrounds the actual Playwright API verification only and does
not claim a CLI argv. The result exposes `native_receipts` and `timings` for
downstream publication. Missing publication capabilities stay explicit limits.

Mutation runtime callbacks run SEC-09, SEC-10 and FUN-06 on nominal and exact
reviewed mutant copies via owned instrumented Linux sessions. A runtime outcome
is `EXPERIMENTAL` only after complete executed check sets and X files containing
those same observations, with matching hashes, check tags and verdict. RFAIL
alone, an incomplete case, stale scope, hardlinked proof or another observation
cannot kill the mutant. No experimental outcome claims acceptance.

Validation: `AUTOSPEC_REAL_LINUX_VALIDATION=1`,
`pytest tests/test_native_quality_raccord.py -q`:
**20 PASS in 7.40 seconds**, JUnit in
`20261012-native-quality-raccord.xml`. Nineteen tests are explicitly offline
mechanism tests with scripted ports/synthetic R, not qualification of a product.
The twentieth really generated its Linux lock, ran pytest plus coverage in the
non-root/network-none product container, exported the observed command/return
code and intact X, and verified unchanged original source. Runtime/browser/
mutation remained PARTIAL because the small collection fixture deliberately
has no independently reviewed application adapter.

Remaining raccords: source reviewed E2E publication helper and the timing/docs
observation ports are maintained by the coordinator owner. All browser execution
must use its confined Linux driver in production; trusted local fixture browser
tests do not prove confinement of generated JavaScript. No remediation task is
closed by this checkpoint alone.

Follow-up after coordinator checkpoint `c9e762e0`: the E2E handoff now uses its
keyword-only `plan_path`, `review`, `source_root` API. Pass a factory-owned
`timing_recorder=NativeTimingRecorder(...)` shared with later build/docker
phases: native split clocks are admitted by `ingest` against the raw exact
execution X; browser is timed through `measure('browser', ...)` with its actual
X/V, not a shell wrapper. The caller must add real build/docker phases before
`publish()`; publication refuses a partial set. Forward
`collection['native_receipts']` to `NativeDeliveryCollector.collect`; receipts
are not an invented observation name or an equivalence to README commands.

Follow-up regression: **89 PASS in 20.66 seconds** with real Linux collection
active. Included raccord (22 tests), exact reviewed plans, hermetic Git,
known-prefix runner accounting, durable tracker reservations and native quality
collector tests. JUnit: `20261012-native-quality-raccord-v2.xml`. This also proves
separate native install/test clock ingestion and refusal of incomplete overall
timing publication. The Git and collector fixture probes remain scoped trusted
metatests, never generated hostile code executed on Windows.
