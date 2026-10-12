# ProbePack source-only/join metadata correction

Scoped implementation in the rem_execution worktree after a normal clean merge
of integration `1ab282e27af0a63e19434abfac478549d82548d6`; no reset/conflicts.
Only production `validation/business_contracts.py` and the new test module
`test_probe_pack_join_metadata.py` changed.

- R-only declarations without handlers can consume all exact intact R checks;
  absent/partial/tampered proofs stay NOT_VERIFIED, negative R stays FAIL.
- `verify(snapshot_hash, *, ids=None)` keeps all checks by default; explicit
  selectors must be nonempty list/tuple, unique and supported by this pack.
- `native_complete` is computed from this execution's identity, native limits,
  and genuinely observed API/DB checks, before supplemental proof consumption.
  Review/UI checks are excluded. Complete failing probes still report FAIL;
  completeness is not passing and cannot alone authorize a backend marker.
- Each native artifact uses a UUID path so repeated verification cannot
  overwrite/invalidate earlier proof bytes.

Receipt `probepack-after-v1.xml`: **36 PASS in 23.43s**, new focused metadata
tests plus existing business and architecture tests. Includes real frozen
contract ARC01/ARC09 exact R positive/absent/partial/tampered/negative cases,
selector admission, missing native execution despite green supplied X,
complete-but-failing execution, wrong identity, and two retained intact passes.

Only supervisor logic and the existing independently trusted SQLite fixture
executed. No provider, Docker, real authentication command, generated product
host execution or generation occurred. Parent owns the separate SEC/browser/
coordinator join implementation and its final combined replay. This scoped
green receipt is neither a global regression result nor launch permission.
