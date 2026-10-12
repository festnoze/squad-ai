# REM-25 launcher — independent RED corrected offline

2026-10-12. Corrective base: 8057d8b5, execution worktree only. Reviewed
independent RED target: integration f66fd7b8. Only launcher, author tests and
REM-25 proofs changed. No real preflight, process, kernel32, HTTP, Docker,
Claude, auth or inference operation was performed.

## Three P1 corrections

1. job_member_identity returns RetainedInterpreter: immutable creation identity
   plus retained OS process handle. Membership in the exact Job remains required.
   Acquisition errors close the handle immediately; successful acquisition does
   not close it. GetExitCodeProcess attests STILL_ACTIVE immediately before POST
   and during monitoring. The handle is closed exactly once in supervisor finally
   after Job/direct-child cleanup, including POST timeout or interruption. The
   production helper always returns that ownership object; inert tests explicitly
   mock the helper with an identity string and therefore perform no OS operation.
2. After Job close, a still-live exact Popen child is terminated through its
   retained process handle and waited for at most ten seconds. Wait timeout causes
   kill of that same owned Popen handle and another bounded ten-second wait.
   This covers failure before the suspended child could be assigned to the Job.
   Cleanup errors are journaled without replacing the original assignment error.
   No lookup or kill by PID/name/path and no global stop is added.
3. monitor_state consumes ProjectState.model_dump: usage.cost_usd,
   usage.unreported_calls, usage.agent_calls; phase/running/paused/error,
   budget_usd/acceptance_result/delivery_ready/generation_checkpoint. Changes in
   any monitored field produce a new STATE record. Pause or running alone does
   not declare completion or acceptance.

All previous environment/model/DTO/source hash/full-brief and Job-containment
constraints remain. No automatic review resolution, retry or product edit added.

## AFTER proofs

- launcher-author-after-v8.xml: 45 PASS, 0.36 s. Original 43 tests adapted only
  for revised ownership/cleanup mock interfaces; two added alive/schema probes.
- launcher-independent-after-v9.xml: 48 PASS, 0.49 s. Same 45 author tests plus
  the three unchanged independent RED counter-tests.
- Independent test source SHA256 before and after replay:
  6394e3f0a6432ed324d8e96c9625ab031b4490af1e83708f3a093732293f6d9c.

Independent test source lives outside this worktree and hardcodes the integration
launcher source path. Replay kept that file byte-for-byte unchanged. A bootstrap
redirected only importlib.util.spec_from_file_location with module name
independent_campaign to the corrected execution launcher. All other imports,
independent assertions and inert mocks were unchanged. Integration was not edited.
The parent will independently replay on the integrated corrected commit.

Runtime: qualified remediation factory-env Python; PYTHONPATH=execution/backend,
PYTHONDONTWRITEBYTECODE=1; pytest -q -p no:cacheprovider; fresh explicit basetemps.
Replay command structure: bootstrap source import routing above, pytest.main
with backend/tests/test_support_benchmark_campaign.py and immutable
C:/Dev/squad-ai/Brainstorming/Autospec/workspace/remediation-20261011/launcher-independent/test_counterreview.py;
--junitxml=artifacts/remediation/REM-25/launcher-independent-after-v9.xml.

These are offline supervisor proofs, not live Windows/Claude admission or a
generated-product verdict. Parent source review/replay and explicit authorization
remain required before any real preflight or --launch.
