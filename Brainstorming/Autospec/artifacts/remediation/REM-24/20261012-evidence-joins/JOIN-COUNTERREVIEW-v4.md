# Independent current-evidence join counter-review

2026-10-12; integration HEAD `e86fff1fe454d983104f11053cc501d29904064a`
plus parent working changes in evidence_join/coordinator/security/browser.
No parent file was edited by this review.

**22 PASS in 2.54s**, receipt `join-counterreview-v4.xml`, independent source
`test_join_counterreview.py`. No remaining reproduced P0/P1 in this bounded
current native/browser join scope.

## Counter-evidence checked

- Actual ProbePack execution on the independently trusted fixture produces the
  initial native-complete/UI-missing FUN02 NV. Store publication demands intact
  X bytes with exact identity, RID, observed-check payload and passed consistency.
  Missing artifact, tampered bytes, wrong snapshot/contract, mismatched observed
  payload and false completeness all fail to publish RID:backend.
- Newly published exact ui_clear X permits only a fresh native replay to reach
  PASS. Descriptive/typo aliases do not satisfy the exact required check. Both
  native UUID artifacts survive with intact hashes after replay.
- Exact ui_refresh and ui_draft X are consumed; FUN06 remains NV without exact
  transaction R and succeeds with the independently supplied intact fixture R.
  A UI witness is not source review, and no reviewed fixture R is claimed as
  future product acceptance.
- Tampered UI cannot publish/promote. Negative UI remains FAIL. Earlier native
  FAIL is retained; earlier incomplete native or current incomplete native cannot
  become PASS. Cross-RID/snapshot/oracle joins are rejected.
- Publishing narrow ARC06:error_client X does not replace full ARC06 verification:
  current native OpenAPI probes still execute and missing public_dto/frontend_errors
  R/native fixture failures block acceptance.

## Source/caller check

`_native_browser_packs` normalizes current pack identities, publishes only
matched native backend X, runs actual browser observers, publishes X/V, then
re-executes only the published crossed SEC/FUN IDs. Failed or missing initial
native work cannot be selected into a green join. ARC's native client contribution
is published before full native ARC verification, never inserted as its complete
requirement result. `_current_rows` rejects changed explicit identities/partial
ID sets before stamping trusted enclosing pack identity onto ProbePack rows.

Browser source now emits ui_clear from the actual missing-detail clearing check,
ui_draft only after the real UX07 sequence, ui_refresh after actual dashboard
mutation/reload/zero-client observations. This review did not execute Playwright
or establish live UI success. Security native completeness is captured after
handler execution and current identity attestation, before missing supplemental
R/V is considered; new security artifacts already use UUID paths.

Reviewed file SHA256 (current WIP bytes):

- evidence_join.py `6bb383b3f9c2fd83e3bfbe00adafd79b2247d51b09b83f84b765308f5040f53c`
- coordinator.py `95c1fe1843840832f083971def8ccbe20e2538852ab38407bc131c6f4a14cb94`
- security_contracts.py `43c8616dd57ad58e183974644e035eb891c8def2419f3b9f26c865c8a6f8430b`
- browser_contracts.py `a66e201b25dc8f69d914f8dda38e3e9ffb10f4b33216d77f89fb9a9f29f6438f`
- architecture_browser.py `764f09793288cba0d8ef015be86aeb77d93e5f2687bb7797d4978cb483abe532`
- business_contracts.py `0991bb01c59a3f11265b72ffe740d66c172d6e10ddfc0c8dd9d5ea95a0ce7b0d`

## Raw history and limits

v1: external test module lacked explicit async-mode; 12 async tests did not run.
v2: 14 PASS/5 FAIL because independent harness omitted production _current_rows
normalization for ProbePack rows; corrected without production changes.
v3: corrected 19 PASS in2.29s. v4 adds three exact alias/source-R cases, 22 PASS.
All receipts retained; harness errors are not production defect claims.

Only supervisor tests plus the existing trusted SQLite fixture executed. Browser
X witnesses and source R in these tests are intentionally independent test doubles,
not actual future product evidence. No provider/preflight/auth/Docker/kernel32,
network HTTP, generation or generated-product host execution occurred. Parent
orchestration metatests, live native collectors, global regression and actual
product acceptance remain separate. This review is not launch authorization.
