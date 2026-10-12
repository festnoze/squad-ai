# Final-path producer matrix — read-only audit

Reviewed integration `1ab282e27af0a63e19434abfac478549d82548d6`, 2026-10-12.
Source tracing only; no new tests, Docker, auth, model, or generated execution.
Qualification concerns wiring, not a claim that any future product probe passes.

## Actual caller chain

`pipeline.py:4544-4570`: fresh frozen snapshot + exact reviewed configuration →
`collect_native_delivery_build` → `collect_native_final_facts` →
`coordinator.verify_project` → `admit_reports`. Final facts invoke native quality
collection, reviewed README/delivery collection, and measured phase publication.
`verify_project` runs SEC/FUN/ARC first, then browser, E2E, quality and operations.
Reviewed source R remains distinct; no native collector fabricates R.

## All eleven EXTERNAL_OBSERVATIONS

| Name | Required consumer | Real producer on the final caller path | Wiring at reviewed HEAD |
|---|---|---|---|
| native_suites | TST-01: native exit, failures, collected/accounted, critical skip/xfail, no nominal DB/security mocks, reviewed assertions/report/collection | `delivery_raccord.collect_native_final_facts` → `collect_native_quality` → `NativeQualityCollector.collect` (`quality_contracts:184-234`) through `_ReceiptValidator`/isolated validator | Present; actual measurement + sealed plan prerequisite |
| requirement_test_mapping | TST-02: all 56 mandatory IDs, executed exact nodeid and reviewed assertion | Same collector `quality_contracts:235,264`, observed suite outcomes + independently reviewed mapping; `_publish_collection` | Present; mapping R alone cannot create execution |
| coverage | TST-03: raw report, full inventory, numerator/denominator, nonzero thresholds/domains/no business exclusions | Same collector `collect` + `_coverage:310`; `_publish_collection` | Present |
| real_sqlite_test_environment | TST-04: isolated real SQLite header, distinct connections, restart, owned cleanup | Native quality callback → `coordinator.sqlite_quality_probe:300-339`; exact runtime/DB export/cleanup | Present |
| browser_e2e | TST-05: exactly six scenarios alone+together, real UI/API/DB, reset, no nominal mocks, nonblank/no console errors, exact X+V mode/source | Native `_BrowserRun.verify_e2e` → `_execute_e2e`; sealed reuse; coordinator fallback; image OPS-03 separately executes scenarios 1+2 | Present for TST-05; not a publisher of SEC/FUN supplemental tags |
| authorization_mutation | TST-06: original PASS, copy FAIL, original untouched, exact original/mutant hashes, executed SEC09/10/FUN06 | `NativeQualityCollector._mutation:330` with `_mutation_callback` → `_mutation_runtime`; independent exact-copy approved profile | Present |
| secret_scan | SEC-01 `scope=source_image_logs`; SEC-15 `scope=logs_artifacts`, intact actual artifacts | No production producer at this HEAD | Known gap already assigned; not newly duplicated |
| cookie_modes | SEC-05: observed HTTPS Secure and explicit loopback-local modes | No production producer at this HEAD | Known gap already assigned; not newly duplicated |
| delivery_build | OPS-01 locked clean build/typecheck/image, actual command/lock/source/image identities | Pipeline direct `collect_native_delivery_build` → `build_delivery_image` → store X | Present |
| docs_audit | OPS-05 README bytes/reproduction obligations/config expurgation/explicit fixtures/no defaults/dated audit | `NativeDeliveryCollector.collect` via `collect_native_final_facts`; publication `delivery_evidence:699` | Present; native executions and independent audit R stay distinct |
| execution_timings | OPS-06 actual machine and install/tests/browser/build/docker phases; reported cost only with X | Shared `NativeTimingRecorder` supplied to native callers; `.publish` (`delivery_evidence:843-868`) | Present, diagnostic-only; incomplete phases remain NV, not estimated success |

## Required checks and producers by pack

- Architecture exact checks (`architecture_contracts:18-45`): ARC01 backend_map/frontend_map/rules/abstractions;
  ARC02 foreign_keys/constraints/null_ids/integer_versions/schema_review; ARC03 distinct_connections/busy/rollback/transactions;
  ARC04 fresh_migration/replay/schema_version; ARC05 query_counts/query_plan/index_rationale;
  ARC06 openapi/validation/public_dto/error_dto/frontend_errors/error_client;
  ARC07 bounds/sorts/totals/detail/no_secrets/refused_unchanged; ARC08 utc/ties/clock/timezone_independent;
  ARC09 domains/http_csrf_errors/typed_dto/duplication_risk. Native `_ARC02..08` supply X;
  named ARCH_REVIEW checks consume exact external R; error_client native browser gap already assigned.
- Business exact checks (`business_contracts:29-45`): FUN01 creation/roles/bounds; FUN02 scope/missing/ui_clear;
  FUN03 priority/assignment/closed/disable_exception; FUN04 matrix/preconditions;
  FUN05 messages/bounds/identity/visibility; FUN06 patch_race/close_wins/message_wins/distinct_connections/transactions/ui_draft;
  FUN07 retry/simultaneous/conflicts/users/rights/restart/closed_replay/durable_constraints;
  FUN08 history/rollback/append_only; FUN09 disable/revocation/assignment_race/reactivate/atomic_disable;
  FUN10 search/bounds/literal/notes/acl_before_page; FUN11 filters/bounds/pagination/sort;
  FUN12 dashboard/refresh/ui_refresh; FUN13 noop/stale_noop/atomic_patch/message_version.
  `_FUN01..13` supply API/DB X; transactions/durable_constraints/append_only/atomic_disable consume R.
- Security `_sec01..15` execute bootstrap/default credentials, normalized uniqueness/races, hashing/bounds,
  login/rate-limit/dummy verification, sessions/entropy/modes, revocation, CSRF/origin, route/role matrix,
  IDOR/idempotency scope, internal-note DTO/search isolation, payload authority, literal XSS/SQL probes,
  last-admin race, immutable accounts and expurgated errors/cache/scan. Requirement types are consumed
  from frozen source; SEC10/12 additionally require V (`security_contracts:230`).
- Browser `BROWSER_IDS`: UX01..08 plus SEC10/12 and FUN02/06/12. Real Playwright methods emit actual
  checks and screenshots, X/V, with frozen bindings/profile. UX methods cover navigation, error/retry/draft,
  keyboard/modal focus, 1280/390 layout, account isolation, search ordering/URL, double-click/conflict,
  internal-note UI. SEC/FUN contributions additionally demand external `RID:backend` tag (`browser_contracts:347`).
- Quality requirements/checks are the six consumers enumerated above; native collector uses a sealed R
  plan, not product success assertions. Delivery OPS02 checks effective confinement/owned volume;
  OPS03 baked-image vertical/health/private anonymous API/scenarios1+2; OPS04 real ticket/response/note,
  restart/undeploy preservation and idempotent replay. `_operations` invokes the actual owned harness.

## Additional concrete blockers, beyond the two already assigned areas

**P1 — browser/backend evidence is not joined before row admission.** Native business expects exact
`FUN-02:ui_clear`, `FUN-06:ui_draft`, `FUN-12:ui_refresh` X proofs (`business_contracts:229-239`).
No producer emits those aliases. Browser methods instead emit descriptive checks such as
`missing_clears_previous_detail` (`browser_contracts:758`) and dashboard/UX07 checks. Native packs run
first (`coordinator:683-692`) and their own proofs are only embedded in returned rows, not published
to the store. Browser then requires `RID:backend`, which no native producer emits. SEC10/12 are NV
before browser because V is missing. `_merge:353-363` appends later proofs but explicitly never raises
NV to PASS or recomputes missing checks/types. Thus even all actual API/DB/browser probes and R
passing cannot make these mandatory rows nominally PASS in the current fresh final path.
Correct join must retain native failures/missing API subprobes; R/GPT cannot invent these X/V tags.

**P1 — R-only ARC01/ARC09 cannot consume complete legitimate review.** Both rows have only checks
in ARCH_REVIEW and intentionally no native `_ARC01`/`_ARC09` handler. Inherited `ProbePack.verify`
unconditionally adds `independent source review required` when no handler exists (`business_contracts:191`).
Even if subsequent supplied proofs satisfy every exact intact R tag, the permanent limit remains;
status at line 249 is therefore NV. This is a nominal consumer bug, not merely absent future review.

No other concrete missing EXTERNAL_OBSERVATIONS producer was found in this short audit.
This does not certify all runtime ports, all possible bindings, full global regression, or future 56-ID PASS.
