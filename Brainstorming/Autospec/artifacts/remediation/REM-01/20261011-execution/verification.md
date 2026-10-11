# REM-01 / REM-02 — execution boundary handoff

Base: ac42b9b2627449af627f32acfe5469ce514ba959 (original user's uncommitted state captured by coordinator). Branch codex/rem-execution. Historical benchmark read-only; no snapshot repair.

## Environment and CLI attestation

Windows, Python 3.14.6 (existing backend/.venv; imports explicitly from this worktree), Node v24.18.0, Claude Code 2.1.296, Docker 29.5.3 Linux engine. Auth status: loggedIn=true, authMethod=claude.ai, apiProvider=firstParty, subscriptionType=team. No credential contents read/copied/serialized; no model call made.

Local `claude --help` supports --restricted, --safe-mode, --tools with empty list, --strict-mcp-config, --disable-slash-commands, --no-chrome, --no-session-persistence. Native `--init-only` probe passed: valid benign sentinel hook and project MCP configuration did not execute. Positive control proved the trusted sentinel script was valid. Inference is tool-less; only the bounded Autospec file broker dispatches operations.

Primary documentation inspected on 2026-10-11: [Claude CLI reference](https://code.claude.com/docs/en/cli-reference), [settings precedence](https://code.claude.com/docs/en/settings). Restricted mode targets shared-machine evaluation harnesses; safe mode preserves authentication unlike bare mode. Tools/customizations are removed, not command-string regex filtered. CLI binary and administrative policy are trusted; a compromised CLI or privileged concurrent host writer is outside this backend's trust boundary.

## Actual tests

From worktree backend: PYTHONPATH=worktree backend, AUTOSPEC_REAL_CLAUDE_PROBE=1, AUTOSPEC_REAL_DOCKER_IMAGE=sha256:074cd835ebd2e8ef19b920118b914d5c76d8fd74404bf7a93f15614084d6b63a.

`C:/Dev/squad-ai/Brainstorming/Autospec/backend/.venv/Scripts/python.exe -m pytest tests/test_runner.py tests/test_providers.py tests/test_runner_processes.py tests/test_restricted_execution.py tests/test_owned_execution.py tests/test_skills.py tests/test_usage_budget_hardening.py tests/test_sandbox.py tests/test_api_provider.py -q`

Observed: **156 passed in 16.84s**, exit 0. Windows: timeout, cancellation during spawn, parent exit/descendant pipes, nested and detached descendants, stale identity refusal, A/B/unowned sentinel preservation, npm literal arguments and shell-shim bypass. Broker: traversal/absolute/ADS/reserved paths, credentials, metadata/oracles, real Windows junctions and hardlinks. Shell/MCP/process requests have no dispatch. Real local FakeCLI subprocess writes main.py and returns final JSON without a model call. Budget is decremented across rounds and usage aggregated.

Docker nominal probe used UID 65532 and wrote only a product result. Hostile code ran ONLY inside a disposable hardened container: host PID stop attempt, broad signal (killed its own disposable child), rootfs write, credential/socket access. Host process/file sentinels stayed intact. Timeout cleanup left no container with its exact run label. Historical images/containers/volumes unchanged; no global stop/prune.

## Integration required before DONE

1. Replace generated-code host execution with `sandbox.arun_isolated(inner_cmd, filtered_stage_root, image, run_id=..., timeout=...)` everywhere. No SANDBOX opt-out or Windows venv path inside Linux. Install networking is separate from execution; REM-05 supplies the attested image/toolchain. This bench used an existing immutable image ID only to qualify the boundary.
2. Mount only filtered product staging, not raw factory workspace: no state/monitor/oracle, .git/.claude/.codex/.agents/.env/credentials or links. Dependency lot supplies stage_project. Export explicit artifact paths only, never arbitrary sync into factory state/oracle.
3. Trusted bootstrap/deploy CLI children use `spawn_owned_process`; cleanup uses `close_owned_process`. `ProcessRegistry(run_id)` supports `.add`, `.resources`, `.terminate(pid, creation_identity)`, `.terminate_all`. No executable-name/current-port/workspace-prefix ownership scans. A Windows Job owns descendants but is not the security boundary.
4. `OwnedResourceRegistry` verifies owner and creation identity. Ports never authorize kills; volumes survive normal cleanup. Cleanup adapters receive a deadline and must enforce it. Docker execution verifies immutable ID and run labels before stop/remove.
5. Claude capabilities: restricted_tools, can_run_shell=false, supports_native_skills=false. Trusted prompt-injected skills may remain; native skills inaccessible. Codex host-shell backend refuses ISOLATION_UNAVAILABLE before spawn. Legacy native Claude sessions cannot resume; mediated history is in-memory/root-bound, so restart needs explicit coordinator recovery, not native resume.

Limits: shared pipeline/bootstrap/deploy/config untouched. Until every generated-code path is connected, integrated factory is not qualified. Docker daemon/OS/kernel and installed CLI remain trusted infrastructure. No claim of VM-strength isolation against compromised infrastructure. Native provider inference intentionally not run to avoid paid usage; flags/init, broker dispatch and nominal subprocess protocol were validated independently.
