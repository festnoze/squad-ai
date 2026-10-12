# REM-20 — native delivery evidence checkpoint

This pack collects actual factory observations. It never manufactures an R,
returns an application's acceptance from a health probe, or turns an attested
cache into an executed installation's exit code. No paid generation/campaign
or historical snapshot was run or changed.

## Integration order (no audit/review circularity)

1. Freeze source and contract. Call
   `collect_manifest_audit(source, snapshot_hash, contract_hash, supervisor_root)`.
   It reads admitted manifests/locks only. Python registry facts go to real
   pip-audit 2.10.1; Node uses actual npm audit. Both networking builds contain
   only manifests/pins and a supervisor constant reporter, no application,
   host dependency tree, package hooks, dotenv, credentials or database. The
   raw result is exported in a separate network-NONE readonly container.
2. A trusted local GPT reviewer receives the frozen brief/reference, source
   facts and these dated raw files, **not** producer-derived expectations.
   `delivery_candidate_schema()` defines the strict fact proposer output.
   `prepare_delivery_proposal(candidate, source_root=..., snapshot_hash=...,
   contract_hash=..., fixtures_fingerprint=...)` attaches actual file hashes,
   returns `AWAITING_INDEPENDENT_REVIEW`, and executes/writes nothing.
3. The independent delivery R must have check
   `PRODUCT:delivery:<proposal.fingerprint>`. Its actual JSON contains
   `configuration_assessments={path:{source_sha256,secrets_found:[...]}}`.
   Findings list keys/locations, never secret values. Add `OPS-05:README` and
   `OPS-05:configuration` to the parent's proof index; the collector cannot
   issue or publish review authority. Insert the R as `plan['review']` and use
   `ReviewedDeliveryPlan.from_dict(plan)`.
4. Every audit finding requires an independent R check
   `OPS-05:audit:<audit_review_subject(raw_audit)>` and actual JSON
   `assessments=[{scope,package,id,severity,exploitable:boolean,rationale,
   arbitration:null|{decision,owner,rationale,date}}]`. Coverage must be exact,
   not just the dangerous findings. Arbitration has a zoned ISO date and an
   accountable rationale/owner. `apply_audit_review(raw,R,evidence_root=...,
   snapshot_hash=...,contract_hash=...)` installs these observations without
   rewriting the raw audit. Tooling is not automatically presumed exploitable
   in production. Empty findings need no invented per-finding assessment.
5. The parent already obtains `build_delivery_image(...,evidence_root=...,
   snapshot_hash=...)`. Its native JSON is published as `OBS:delivery_build`.
   Coordinator OPS-01 calls `delivery_build_checks`: exact manifest+lock+recipe
   and complete input fingerprints, real cache/layer builders, composite
   tsc/Vite rc, fresh current Docker IDs and labels. Installs retain rc=None.
6. Open a **fresh direct** OwnedProductHarnessSession before any prepare_case.
   Construct `NativeDeliveryCollector(plan,source_root=...,evidence_root=...,
   snapshot_hash=...,contract_hash=...)`; call `await collect(harness,
   build_receipt=...,native_receipts=...,audit=classified_audit)`.
   It executes migration, observes zero pre-fixture users, then runs explicit
   reviewed fixture inputs. README source and reviewed configuration byte
   identities are checked before publication of `OBS:docs_audit`.

## Command mapping

Every mapped row contains `label`, `obligation`, `documented_text` (literal
README substring), `argv` (actual reviewed argv) and `execution`. Production
requires all nine obligations: install/tests/coverage/e2e/launch/seed/migration/
backup/restore. Missing obligations remain NV, even with migration success.
Trusted narrow metatests can explicitly reduce their scope; external candidate
JSON cannot do so and coordinator OPS-05 always requires the complete set.

- `runtime`: `action`, `parameters` — exact reviewed CommandBinding executed
  inside owned live runtime; migration first, backup/restore thus target its
  exact controlled DB, not a copied/exported or host database.
- `isolated_command`: `root`, `ecosystem` — literal argv via
  IsolatedValidator.run_captured(mode='test') on a fresh filtered stage/deps in
  Linux NETNONE. E.g. README `pytest -q` runs actual `pytest -q`, not a fictitious
  equivalence to the reporter wrapper. Actual rc and stdout/stderr digests are
  retained in X; raw output is withheld because producer logs can leak secrets.
- `runtime_launch`: exact source-reviewed RuntimeSession command, current owned
  running container inspection; rc=None with `execution='observed-runtime'`,
  never a made-up successful process exit.
- `fixture_provisioning`: `action` — exact seed argv actually executed during
  reviewed fixture provisioning, with its native rc and explicit input identity.
- `build_attestation`: `receipt_kind` backend_install/frontend_install — exact
  immutable factory recipe argv, attested-cache/layer and rc=None.
- `native_receipt`: `receipt_name` — `native_receipts[name]={argv,return_code,
  proofs:[Proof X]}`; the intact actual raw file must contain that argv and rc
  (direct object or `commands` list). A Playwright API call is not a CLI and
  cannot be presented as one. Use a real declared isolated E2E CLI, or report
  missing README reproduction, instead of inventing an argv.

Source commands unknown to the reviewed bindings, browser binaries absent from
an isolated CLI environment, non-public/multi-version Python audit exports,
unavailable registries and unsupported tool report formats remain NV. No host
script/config/import fallback exists. The advisory auditor covers known public
advisories only, not arbitrary package malice or complete exploitability.

## Native clocks and E2E handoff

`NativeTimingRecorder(evidence_root=...,snapshot_hash=...,contract_hash=...)`:
`await measure(phase,async_operation,proof_provider)` or
`measure_sync(phase,sync_operation,proof_provider)` measure actual monotonic
durations with already obtained X/V. `ingest(phase, timing, actual_X)` accepts
only timing/environment_preparation objects equal to raw execution receipt
bytes; it keeps actual install and test clocks separate, not a combined guess.
`await publish()` observes Python/OS/CPU/Docker server and publishes
`OBS:execution_timings` only when install/tests/browser/build/docker all exist.
LLM cost appears only with an actual recorded cost X, marked reported; no cost
or elapsed-time estimate is manufactured and no scenario is deleted for speed.

For prior real twelve E2E source runs, call
`publish_reviewed_e2e(store,runs,plan_path=quality-review-package.json,
review=exact_quality_R,source_root=...)`. Reuse rechecks plan/mapping/source,
all six IDs in both modes, frozen expectation, same hashes and raw X checks/
mode/source_expected plus scoped V. Missing/changed seal reruns source probes.
OPS-03 baked-image runs always execute separately; namespace `image_id=None`
never supplies production-image evidence.

## Tests and limitations

Before final checkpoint: 25 PASS/40.43s, including actual Linux locked install,
tsc/Vite/image/attested-cache validation and actual pip-audit; 3 PASS/43.82s for
README selection (one plan unit and two actual Linux good/bad CLI/SQLite cases).
57 PASS/6 explicit opt-in SKIP/1.50s latest targeted unit regression.
The first README run correctly rejected the legacy test fixture's unpaired
fixture fingerprint (2 FAIL, 1 PASS/34.81s); the fixture was sealed, not the
production rule relaxed. Its JUnit remains preserved separately.

The real README fixture is intentionally narrow: it proves migration, zero
default users, explicit real Argon2 accounts/SQLite seed, actual isolated pytest
and launcher, plus a deliberate rc9 reproduction failure. It does **not**
declare complete OPS-05, all six source E2E or support-client's 57 criteria PASS.
An audit declared unavailable remains NV despite those native successes.
