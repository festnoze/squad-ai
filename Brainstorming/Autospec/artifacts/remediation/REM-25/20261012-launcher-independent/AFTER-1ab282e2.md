# Independent launcher AFTER — scoped offline qualification

2026-10-12; reviewed clean integration HEAD
`1ab282e27af0a63e19434abfac478549d82548d6`.

**51 PASS in 0.90 seconds**: 45 current author launcher tests, the same three
independent counter-tests from the RED review **unchanged**, plus three
FakeRunner/unknown-provider receipt tests. Receipt:
`independent-after-1ab282e2.xml`. The original RED source and XML remain retained.

## Three P1 findings resolved in this scope

- `RetainedInterpreter` keeps the successfully admitted actual interpreter
  handle and its creation identity. The helper closes on admission failure,
  not success. Before POST and during supervision, `assert_alive` checks the
  exact retained handle using `GetExitCodeProcess`; the owner finally releases
  it, with idempotent close. Exact Job-membership checks remain intact.
- Cleanup now attempts exact retained Popen termination if the owned process
  remains alive, including when Job assignment failed. The bounded wait/kill
  fallback remains scoped to that Popen process, not PID/name/path discovery.
  Job close still covers assigned descendants; errors are recorded. The
  previously RED independent assignment-failure test is PASS unchanged.
- `monitor_state` uses the actual ProjectState schema: nested usage cost and
  unreported/agent-call counts; paused/running/error; acceptance_result,
  checkpoint and delivery readiness. The previously RED real ProjectState
  cost/pause/error/NV transition is now recorded and PASS unchanged.

No remaining P0/P1 finding identified in the requested launcher corrections
and offline admission/ownership/monitoring scope.

## Small FakeRunner correction

Diff against the reviewed RED integration changes only the empty inert
FakeRunner queue error to attach an explicit zero-usage AgentResult. No real
provider error handler or missing-cost guard is relaxed by that correction.
The three focused tests pass: empty fixture has known zero receipt; a later
known inert reply can proceed; a real-style AgentError with absent receipt
increments unreported calls, then blocks the second dispatch with
`COST_UNREPORTED`, and the underlying runner is called exactly once.

The historical fourth global run remains RED as documented; this scoped
51-test replay does not replace it or certify the global suite/native probes.

## Limits and authority

Only offline mocked tests and read-only source inspection were performed.
No actual preflight/auth/Claude/Docker/network HTTP/subprocess creation/kernel32
call/inference/generation or generated-product host execution occurred.
Actual installed CLI/auth metadata, Linux Docker/NETNONE execution, live
Windows venv redirector/Job/health behavior and native acceptance collectors
remain unverified here. No integration file was changed; post-run Git status
was clean. This review is not authorization to launch.
