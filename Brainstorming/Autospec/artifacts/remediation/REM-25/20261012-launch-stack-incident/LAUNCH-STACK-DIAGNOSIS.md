# REM-25 launch stack diagnosis — same-project recovery only

Read-only, 2026-10-12. Existing campaign
`workspace/relais-support-rem25-20261012-final`, project
`relais-support-rem25-20261012-fi-0e6ebc49`, port8130. No implementation,
project, provider, generated code or running factory was modified by this review.

## Reproduced from retained source and state

Launcher `payload` (`tools/support_benchmark_campaign.py:127`) supplies display
labels as machine values:

    {"backend":"Python/FastAPI","database":"SQLite","frontend":"React/TypeScript/Vite"}

`CreateProjectRequest.technical_stack` is only dict[str,str] (`api/server.py:313`).
`acreate_project` persists it unchanged, then starts the pipeline (`:586-601`).
`Pipeline._aselect_stack` first calls `_aselect_language` (`pipeline.py:2659`),
whose explicit-backend branch immediately casts to BackendLanguage (`:2557`).
Enum values are python/go/rust/node (`models.py:62-68`), not prose labels.
This fails before resolver/bootstrap/generation, with exactly the retained error:
`'Python/FastAPI' is not a valid BackendLanguage`.

The later resolver also expects canonical lowercase frontend/database values
(`stack.py:173-278`), so changing only backend in the launcher would expose the
next React/SQLite mismatch. `bootstrap.py` consumes the resolved technical_stack;
there is no separate permissive BootstrapSpec display-label parser here.

The current state confirms needs_attention, bootstrap_status=failed, empty
bootstrap_fingerprint/stories, backend_language=python default, unchanged bad
technical_stack, budget40, cost0, agent_calls0, failed_calls0/unreported_calls0.
The supervisor journal records one CREATE_ATTEMPT and CREATED for this exact ID.
The exclusive creation marker remains outcome=UNKNOWN by design; the CREATED
journal and persisted state establish identity without a second POST.

## Smallest correction and offline regression scope

Root source writer should change only launcher machine payload and its erroneous
expected-value test to:

    {"backend":"python","framework":"fastapi","frontend":"react",
     "database":"sqlite","kind":"fullstack","source":"explicit"}

Keep normative brief/reference/source-fact hashes, max7lots and budget40 unchanged.
Existing launcher test currently asserts the bad display strings at line102;
its green result never verified composition with the real stack contract.

Required narrow new regression: compose actual launcher payload through
CreateProjectRequest/ProjectState, then BackendLanguage cast and stack.resolve/
freeze; assert exact canonical five decision fields and stable decision SHA.
Exercise `_aselect_stack` with a fail-on-dispatch inert runner: source-pinned
nominal must finish selection with correct streams and zero agent calls before
any bootstrap execution. Preserve the invalid-label RED as a negative; do not
make generic stack resolution accept ambiguous display strings just for this run.
No Docker/bootstrap/product execution or inference is needed for these tests.

## Existing same-project metadata-only recovery

Root can use the existing trusted control endpoint, after re-attesting idle
same ID, failed/unfingerprinted bootstrap, no active task/deployment and zero usage:

    PUT /api/projects/relais-support-rem25-20261012-fi-0e6ebc49/language
    {"language":"python"}

`Pipeline.aset_language` (`pipeline.py:2800-2811`) allows this failed,
unfingerprinted state, sets backend_language=python and replaces bad partial
technical_stack with backend=python/source=explicit, then persists metadata.
It performs no runner call, bootstrap, product generation, budget reset or new
project creation. Exact original brief and fullstack profile then deterministically
resolve frameworkfastapi/frontendreact/databasesqlite at a future authorized start.

Only propose this endpoint; this reviewer has not called it. Follow with read-only
state inspection and an appended recovery journal/receipt, preserving original
input.json, creation marker, run ID, contract/source hashes and all cost evidence.
Do not rewrite the original malformed request as though it had always been valid.

Do **not** call resume-build as part of a no-paid/no-product-write correction:
the failed-bootstrap/no-stories branch (`pipeline.py:9239-9243`) calls start and
can progress into real bootstrap writes and provider dispatch. That endpoint is
the existing same-project continuation once root separately authorizes resumed
generation after the canonical-payload offline regressions and metadata review.
Do not call restart (it wipes derived state/resets usage), retry-failed, a second
campaign creation, or stop/restart the owned factory merely to fix request values.

This is an actual nominal launcher integration defect, not a Claude/Windows/
Docker/auth failure and not a generated-product failure. The earlier native
supervisor probe intercepted before POST and could not exercise this contract.
