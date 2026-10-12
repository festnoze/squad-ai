# Paid receipt survives cancellation/error of supervisor cleanup

Counter-review: `_UsageTracker._arun` previously awaited transient claim release
before accounting a successfully returned paid result. `CancelledError` or
another cleanup failure replaced that result. In the concurrent lane the whole
reservation stayed unknown despite a known receipt; in the default serialized
lane the known cost could disappear from the project and the next remaining
allowance. This was not a provider-budget capability or a free call.

The result is now accounted synchronously immediately after provider return,
before any cleanup await. Known incomplete error/cancellation prefixes are also
retained locally. Cleanup cancellation carries the original `usage` receipt;
other cleanup errors become `AgentError(SUPERVISOR_CLEANUP_FAILED, usage=...)` so
the outer journal reconciles that same receipt. There is no second accounting.
Execution/process/skills/budget contexts are restored even if release fails.
Complete known costs release only the unused reservation; incomplete known
prefixes retain the unreported remainder and block further admissions.

Validation: 76 PASS/4.11s across cleanup tests, tracker reservations, mediated
known prefixes, general USD/token budget hardening and durable reservation
mechanics. Nine new cases cover OFF/default serialization and concurrent lane,
cancellation and normal cleanup errors, complete/incomplete receipts, replaced
provider error prefixes, exact state cost/token counters, remainder reservation
and restoration of contexts. These are scripted offline ports/costs and
synthetic provider-proof fixtures, NOT qualification of Claude or any real
provider. No paid API/model call was made. REM-23 remains OFF with no production
provider proof by default.

JUnit `20261012-tracker-cleanup-v3.xml`; earlier v2 31 PASS/1.29s and the initial
no-tests attempt (incorrect legacy filename) are preserved separately. Changes
are limited to the `_UsageTracker._arun` section, not claim authorization or
acceptance pipeline sections owned by the parent.
