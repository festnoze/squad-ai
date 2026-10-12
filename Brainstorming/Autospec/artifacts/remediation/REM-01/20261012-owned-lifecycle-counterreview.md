# Owned delivery lifecycle counter-review corrections

Scope: external publication/package journals and their facades. No pipeline,
API, product source, source reviewer, configuration, or shared tracker mutation.
No paid provider call. Human authorization covered trusted local supervisor
tests and owned Docker probes; product fixture code runs only inside hardened
Linux Docker NETNONE, without a Docker socket, host source overlay, or credentials.

## Verified behavior

- Intentional package detach and completed publication stop/data destruction
  report `skipped=True`, not failed deployment. Missing live resources,
  uncertainty, and incomplete `stopping` remain explicit non-successes.
- Completed publication stop status is journal-only: an unavailable daemon or
  subsequently removed image does not recreate an intentionally retired service.
- Reuse rechecks the source snapshot after actual alias/container/HTTP
  inspection, before admission. A concurrent source edit refuses the call and
  preserves the old qualified alias/app/DB. Explicit recovery of an immutable
  former service is not contingent on mutable producer source remaining unchanged.
- Publication return `created_this_call` is transient, never a journal field.
  `DockerDeployResult.created_publication_container` contains the exact new CID
  only for a container created by this successful publish call under the registry
  lock. It is empty for reuse/adoption/recovery, including crash-before-state-flush.
- Late cancellation cleanup accepts `expected_publication_container` at the
  facade and `expected_container_id` at the registry. The locked current journal
  and freshly attested CID must match; a later replacement is preserved.
- Cold adoption cancellation releases only the newly acquired local ingress;
  an already running qualified daemon app and its DB survive. Recovery forwards
  an optional cancellation event and never returns a creation cleanup receipt.
- Stop durably writes `stopping` BEFORE relay/container/migration cleanup.
  Failed intent persistence changes no resources. Failed cleanup or terminal
  persistence cannot revive the service: every recovery of `stopping` is refused.
  Another explicit stop may finish the same intent, retaining DB. A receipt-bound
  retry admits an already missing CID only when the durable stopping journal
  still names that exact CID. Original errors propagate; no fake stopped success.

## Root integration

After a cancelled/failed publication call, clean up only when
`result.created_publication_container` is nonempty:

```python
undeploy(project_id, publication_root=external_root,
         expected_publication_container=result.created_publication_container)
```

Never derive creation authority from UI state/CID differences. User-requested
normal stop omits the receipt filter. Supervisor startup recovery must retain
the parent `intended_active_only=True` gate and track/shield/drain its worker;
this patch adds only `cancel_event=None` forwarding to that facade.

Absent journals inspect as `registered=False` / facade `skipped=True` without
ANY Docker query or mutation. Strict cleanup returns exact
`PUBLICATION_NOT_REGISTERED` or `PACKAGE_NOT_REGISTERED`; those strings grant no
legacy/name/SHA deletion authority. A contractual project never published can
be logically deleted after both journals are absent and no state resource is
claimed. Claimed resources without either journal require explicit disposition.

## Evidence and limits

The first lifecycle native replay passed **55 tests in 176.57 s**
(`20261012-owned-lifecycle-native-v2.xml`). The replay including stop-intent
counterexamples passed **58 tests in 194.06 s**
(`20261012-owned-lifecycle-native-v3.xml`). Both include real baked image HTTP,
SQLite persistence, exact daemon/volume ownership, real Windows owned-factory
process death and restart, migration-before-plain-CMD, and unrelated host/shared
image canaries. All product execution remains Linux NETNONE. Existing actual
identity receipts are retained in `publication-native.json`,
`publication-prelaunch-native.json`, and `package-native.json` from their original
campaigns; these are not relabelled as fresh results.

Stop-intent factory-only replay: **53 PASS / 5 native deselected, 22.09 s**
(`20261012-owned-lifecycle-stop-intent-unit.xml`). Final factory replay also covers
journal-only completed-stop status and cancellation forwarding:
**55 PASS / 5 native deselected, 19.35 s**
(`20261012-owned-lifecycle-stop-intent-unit-v3.xml`).
The v2 replay (**54 PASS / 1 FAIL / 5 deselected, 20.15 s**) is retained: its new
cancellation test callback omitted the Python method receiver and raised
`TypeError`. Correcting that trusted test callback does not weaken assertions or
change the production cancellation behavior.

These scoped tests do not replace independent business acceptance or a global
green regression. Publication remains local IPv4 loopback, fixed SQLite path,
Python/Node only, explicit startup recovery, and same-qualified-image updates
only. No arbitrary network publication, cross-version migration, complete disk
quota, or automatic resolution of uncertain/stopping journals is claimed.
