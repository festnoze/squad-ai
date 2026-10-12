"""Actual factory Git timing diagnostics, not a product speed acceptance gate."""
import json
import os
import time
from pathlib import Path

from autospec.orchestrator.git_boundary import git_invocation, run_git


def test_owned_git_command_latency_is_measured_without_relaxing_containment(tmp_path):
    root = tmp_path / "isolated-git-diagnostic"
    root.mkdir()
    rows = []
    commands = [
        ["init"],
        ["config", "user.name", "Synthetic factory latency probe"],
        ["config", "user.email", "synthetic@example.invalid"],
        ["add", "-A"],
        ["commit", "--allow-empty", "-m", "Synthetic empty baseline"],
        ["status", "--porcelain"],
        ["rev-parse", "HEAD"],
        ["status", "--porcelain"],
        ["rev-parse", "--show-toplevel"],
    ]
    for argv in commands:
        started = time.perf_counter()
        git_invocation(root, argv)
        preflight = time.perf_counter() - started
        started = time.perf_counter()
        code, output = run_git(root, argv, timeout=30)
        elapsed = time.perf_counter() - started
        rows.append(dict(argv=argv, return_code=code, preflight_seconds=preflight, total_seconds=elapsed))
        assert code == 0, output
    destination = os.environ.get("AUTOSPEC_GIT_LATENCY_EVIDENCE")
    if destination:
        path = Path(destination)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(dict(
            scope="Measured synthetic local Git bookkeeping; no product acceptance or timing threshold",
            os=os.name, commands=rows, total_seconds=sum(r["total_seconds"] for r in rows)),
            indent=2), encoding="utf-8")
