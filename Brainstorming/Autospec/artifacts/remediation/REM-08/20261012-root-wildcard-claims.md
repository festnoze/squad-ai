# REM-08 — first-segment wildcard claims

Code commit: `2bc31a1f`. This is a deterministic claim fix, not campaign acceptance.

The old static prefix interpreted `test*.py` as the literal ancestor `test`,
although `test_auth.py` matched the glob. It could therefore reserve two writers
for the same concrete file. A wildcard inside the first path segment now has an
empty literal ancestor, so overlap is conservatively assumed. Complete literal
directories still prove disjointness (for example `src/test*.py` and
`other/test_auth.py`). No pipeline or paid-model change was made.

Coverage includes `test*.py`, `[ab]*.py`, `foo?/x`, `foo*/x`, nested wildcard
prefixes, cross-stream serialization, active reservations from outside the
incoming batch, simultaneous reservations, read/read sharing, and read/write
conflict. A real FileBroker write batch uses the real ClaimArbiter via its
pre-write callback: the refused owner creates neither file, the authorized
owner writes the expected content, and a subsequent refused write preserves it.

Locked factory environment, worktree `backend`:

```
python -m pytest tests/test_canonical_claims.py tests/test_independence.py -q --junitxml=../artifacts/remediation/REM-08/root-wildcard-claims-v2.xml
```

Result: **45 passed, 0 skipped, 76.21 seconds**. The preceding 44-test run is
retained as `root-wildcard-claims-v1.xml` (44 passed, 81.53 seconds).

Limit: overlap intentionally over-serializes root-level wildcard claims when
disjointness is not provable. Concrete write scope remains path-matched; this
change does not grant the wildcard owner permission to arbitrary files. The
existing asyncio arbiter is exercised in-process, not as an inter-process lock.
