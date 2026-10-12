# Bounded atomic supervisor journal replacement on Windows

Code: `07348ec6`, limited to `dependencies.atomic_json` and its dedicated tests.
No publication, storage, pipeline, manifest or acceptance-boundary code is changed.

Diagnosis: the read-only parent JUnit
`C:/Dev/squad-ai/Brainstorming/Autospec/workspace/remediation-20261011/owned-publication-parent-20261012.xml`
(SHA256 `3f87034dd93ab8a2663b1b6c93c8d21ee4b149125dd8a032ca15ec63e9324c07`)
records18 PASS /1 FAIL /75.46s, with both native Docker probes passing. The
failure is `test_drift_or_foreign_resource_never_adopted_executed_or_removed[created]`:
setup's second committed-project journal swap raises WinError5 before the
deliberate drift mutation. The original trace proves a replacement refusal,
not which process or ACL caused it. No parent artifact or foreign resource is
edited or adopted by this fix.

`storage.save_project_file` already uses bounded backoff but retries all I/O
and has optional best-effort persistence. This journal remains required and
fail-closed: only the atomic swap retries, only for native `winerror`5,32,33.
Maximum five attempts reuse the same completely serialized and fsynced temp
in the destination directory; delays0.05/0.10/0.15/0.20s total0.50s. A permanent
denial rethrows the original exception after the bound. JSON serialization,
fsync, unclassified POSIX EACCES, missing-file, disk-full and cross-volume
errors are not retried. There is no chmod, target unlink, target truncation,
non-atomic fallback, or fabricated successful checkpoint. The existing final
temp cleanup is preserved; `atomic_bytes` and other persistence APIs are unchanged.

Verification uses the locked factory Python from the worktree backend with
fresh owned basetemps, never product execution on the host:

- `atomic-v1.xml` / `.log`:32 PASS /1.29s, dedicated atomics and dependencies.
- `regression-v2.xml` / `.log`:58 PASS /2 explicit Docker opt-in SKIP /12.01s.
- Final `regression-v3.xml` / `.log`:60 PASS /2 explicit Docker opt-in SKIP /13.51s:
  `tests/test_dependencies_atomic.py tests/test_rem_dependencies.py
  tests/test_storage.py tests/test_owned_publication.py`.
- The dedicated final atomics include16 controlled-error cases and two REAL
  Windows kernel cases, not skipped: `CreateFileW` opens an ordinary owned
  fixture with read/write sharing but WITHOUT delete sharing. The kernel first
  refuses rename; releasing that handle during backoff allows the complete
  new JSON to commit (0.165s). Holding it throughout the bound produces a real
  error and preserves the old bytes (0.522s). The handle is always closed.
- Controlled probes verify exact attempts/delays, same temp, fsync before swap,
  old bytes on every refused attempt, old JSON after permanent failure, temp
  cleanup, no target deletion/permission mutation, first-write no partial
  journal, and no retries after serialization/fsync failure.

An initial proof-directory command used a wrong relative directory and failed
redirection BEFORE pytest launched; it produced no test result and is not
counted above. Corrected commands use the listed artifact directory.

Limits: the parent Docker tests are not rerun here (opt-in disabled); their
prior PASS is not relabeled as a new run. This does not identify the original
locking actor, authorize an ACL change, guarantee that permanent denial can be
recovered, add directory-fsync crash durability, or resolve unrelated global
suite failures. The bounded wait is synchronous, so async callers still own
offloading it as they do other filesystem operations.

Primary references: [Microsoft system error codes](https://learn.microsoft.com/en-us/windows/win32/debug/system-error-codes--0-499-)
defines5 access denial and32/33 sharing/lock refusal;
[CreateFileW sharing semantics](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-createfilew)
documents that deleting/renaming requires compatible delete sharing until the
open handle closes. This supports the chosen controlled kernel reproduction,
not an inference that every WinError5 is transient.
