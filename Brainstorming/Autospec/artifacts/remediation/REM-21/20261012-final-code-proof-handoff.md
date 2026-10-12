# Final code/proof handoff checkpoint

Code commits, separate from this evidence bundle:

- `162ed678`: source-reviewed baked CMD/recipe/ENTRYPOINT admission, strict JSON
  NativeSuiteSpec conversion, and typed `NativeTimingUnavailable`.
- `d3777075`: full bounded no-follow Git metadata preflight, including real
  linked-worktree/common directories and refs/objects/logs descendants.

CMD evidence: REM-20 `reviewed-cmd-native-v1.xml`, **27 PASS / 51.30s** against
peer `a2b076ab`. Real Linux tsc/Vite/cache/image inspections, exact four build
subclocks, Python `main:app` with no `__main__`, plain Node ESM image startup,
and deliberately mismatched image CMD refusal. Native receipt bytes remain in
REM-20 `native-reviewed-cmd-evidence`; they are historical synthetic fixture
snapshots, not full product acceptance. Docker may omit an actually empty
Entrypoint JSON key; omission/null/[] is absence, whereas an inherited script
fails. The Node factory recipe briefly uses USER 0 only for its constant global
dependency symlink, then restores 65532 before runtime. No source overlay or
RuntimeSession argv correction can replace the baked image command proof.

`coordinator-seal-and-cmd-unit-v6.xml`: **74 PASS / 9 opt-in SKIP / 2.19s**.
Includes all eight E2E seal cases after JSON arrays are explicitly converted to
tuples, without hash changes; malformed/extra fields and values remain refused.
Earlier v4/v5 retain new fixture setup errors (missing requirements, str vs
Path) and the NaN exact-raw guard. Those fixture errors were corrected, not
the fail-closed source/receipt/clock checks. `NativeTimingUnavailable` denotes
only unusable diagnostic subclocks; stale X, raw mismatch, source/image/recipe
contradiction and duplicate ingestion retain plain `AdapterUnavailable`.

`legacy-four-files-full-v3.xml`: **128 PASS / 103.73s**, all four complete
legacy modules plus Git boundary. Earlier six failures were not silenced:
coherent mocked Git ownership and an explicit resolver port repaired fixture
bugs; strict local merge-base/revert fixed two production omissions.

`git-metadata-preflight-native-v2.xml`: **40 PASS / 16.78s**, no skip. Real
Windows junctions at refs/heads, objects/pack and logs/refs/heads, plus a real
hardlink ref, are refused before any Git subprocess. Their external owned test
sentinel is unchanged. Real normal repo/linked-worktree/merge/revert and semantic
canary/scope paths remain runnable. v1 retains three nominal failures caused
by Windows DirEntry cached st_nlink=0; fresh os.stat(no-follow) corrected that
without accepting hardlinks. The metadata scan is bounded at 200,000 entries;
larger/inaccessible/special metadata is refused rather than silently skipped.
It is a preflight, not protection against a hostile external writer racing the
scan; the producer still cannot write `.git` through the broker.

No new paid generation, benchmark or user/historical snapshot/database change.
The global regression run is not declared green from these scoped results.
The parent owns final pipeline/bootstrap review and acceptance decisions.
