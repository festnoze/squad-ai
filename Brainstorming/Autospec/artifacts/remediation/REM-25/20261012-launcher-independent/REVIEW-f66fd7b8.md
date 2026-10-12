# REM-25 independent launcher qualification — RED

Reviewed integration commit `f66fd7b85387b15a5bdbf949bee5b4fb20e8ea60`, 2026-10-12.
Read-only target: launcher, its 43 offline tests, preparation/preflight-plan documents,
normative support-client v0.2 sources, and directly relevant config, Windows Job,
health endpoint, project-state/API serialization and fullstack-profile contracts.
No integration file was modified. No launch permission is granted.

## P1 findings reproduced offline

1. **Actual interpreter handle is not retained through admission.**
   `tools/support_benchmark_campaign.py:231-232` closes the `OpenProcess` handle
   in `job_member_identity` before returning its creation-identity string.
   The supervisor consumes that string at line 262, journals it, then creates
   the project. For a venv redirector, the retained Popen handle belongs to the
   redirector, not necessarily the actual interpreter. Membership is checked,
   but the actual interpreter's handle is discarded before POST, contrary to
   the explicit retained-OS-handle contract. The independent mocked kernel32
   test records `CloseHandle(99)` before the helper returns. Retain an owned
   actual-process handle through POST/ownership lifetime and release it only
   in supervisor cleanup, preserving membership/creation identity checks.

2. **Job-assignment failure does not terminate the newly owned suspended child.**
   `supervise` creates suspended Popen then calls `assign_and_resume` at line
   247. If `AssignProcessToJobObject` fails, that process never belongs to the
   Job. The finally path at lines 290-292 closes the Job and waits for the
   process, but never terminates the direct child by its retained Popen handle.
   A suspended unassigned child cannot exit through Job kill-on-close; a real
   wait can time out and mask the original error while leaving that owned
   process behind. The independent inert assignment-failure test observes
   only `closed`, `wait`, with no direct owned-child termination. Add bounded
   cleanup of that retained direct child when containment was not established;
   do not use process-name/PID/global cleanup.

3. **Supervisor misses actual cost, pause/error and acceptance changes.**
   Line 274 reads top-level `status`, `cost_usd`, `acceptance_verdict` that are
   not the `/api/projects/{id}` schema. That endpoint returns
   `ProjectState.model_dump(mode='json')`: cost is `usage.cost_usd`, and state
   includes `running`, `paused`, `error`, `acceptance_result`. The independent
   test uses two real ProjectState serializations: cost 1 then 7, with paused,
   `COST_UNREPORTED` and `NOT_VERIFIED` added without phase/budget change.
   Only one STATE record is produced, with null cost/status/verdict. This hides
   actionable blocking states from the foreground operator/journal, although
   it does not itself bypass the core budget gate. Monitor the actual schema
   without claiming pause/running alone define campaign completion.

## Test receipts

- `independent-red-final.xml`: **43 PASS / 3 FAIL**, 1.44 seconds. Existing 43
  assertions preserved; three independent safety/operational counter-tests RED.
- `test_counterreview.py`: independent test source, no production edits.
- Initial restricted run hit temp-directory WinError 5, not a product finding.
- `independent-red.xml`: first permitted run, 43 PASS / 3 FAIL; the third failure
  was an independent fixture error (missing required ProjectState goal). Goal
  was corrected and the final receipt reproduces the real monitor failure.

Command: supplied factory-env Python, `PYTHONPATH=<integration>/backend`,
`PYTHONDONTWRITEBYTECODE=1`, `-m pytest` existing launcher tests plus independent
counter-tests, `-q -p no:cacheprovider`, fresh dedicated basetemp and JUnit XML
under this independent directory. Scoped escalation was used only after the
restricted temp-directory denial.

## Positive evidence and limits

The 43 existing tests support clean-commit/hash checks, read-only mocked
preflight, complete payload, pinned environment/effective settings/fullstack
composition, all eight mandatory CLI-interface flags, no reuse/retry/budget
reset, nominal inert single creation, readiness mismatch blocking POST, and
mocked owned-Job lifecycle/membership. The installed dotenv load is intercepted
before fresh Autospec imports in source; fullstack overrides do not reactivate
the prohibited LLM flags. Reviewed budget wording correctly distinguishes
fresh estimated $40 from a billing hard cap.

These checks are offline only. No actual preflight, authentication, Claude,
Docker command, inference, generation, generated-code host execution, network
HTTP call, subprocess creation or Windows kernel32 call occurred. Existing
supervisor tests mock all these boundaries; independent tests also mock them.
Actual CLI/auth shape, Linux engine availability, live NETNONE execution,
Windows redirector/Job/health behavior and native acceptance collectors remain
unverified operational prerequisites. REM-24/global qualification and separately
reported SEC/ARC native-collector gaps are outside this review.
