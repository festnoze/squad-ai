"""Run one bench cell (config x project x repetition) and judge it with the hidden oracle.

From backend/, venv active:
    python -m bench.run --config c --project B1 [--n 1] [--model sonnet] [--cap-s 1800]
    python -m bench.run --oracle-only --project B2 --workspace PATH [--config v1-legacy]
Results: docs/bench/<date>/<config>/<project>-<i>.json, then `python -m bench.report`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

from bench import proc
from bench.briefs import Brief, load_brief
from bench.oracle import judge
from bench.paths import BACKEND_DIR, DOCS_BENCH_DIR, REPO_DIR, WORKSPACE_BENCH_DIR

HARNESS_SYSTEM = "You are a senior Python developer working alone in this repository."


def _git_sha() -> str:
    out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=REPO_DIR, capture_output=True, text=True)
    return out.stdout.strip()


def run_v2(brief: Brief, run_dir: Path, cap_s: float, model: str) -> dict:
    """Config C: the v2 core through its CLI, killed with its whole tree at the cap."""
    brief_file = run_dir / "brief.md"
    brief_file.write_text(brief.body, encoding="utf-8")
    argv = [sys.executable, "-m", "autospec.core", "run", "--name", brief.name, "--package", brief.package,
            "--profile", brief.profile, "--brief-file", str(brief_file), "--workspace-root", str(run_dir),
            "--model", model]
    result = proc.run(argv, cwd=BACKEND_DIR, timeout_s=cap_s, stdout_path=run_dir / "factory.stdout",
                      stderr_path=run_dir / "factory.stderr")
    summary: dict = {}
    for line in reversed(result.stdout.strip().splitlines()):
        try:
            summary = json.loads(line)
            break
        except json.JSONDecodeError:
            continue
    workspaces = [p for p in run_dir.iterdir() if p.is_dir()]
    usage = summary.get("usage", {})
    return {"completed": result.returncode == 0 and summary.get("phase") == "done",
            "phase": summary.get("phase", "timeout" if result.timed_out else "unknown"),
            "error": summary.get("error", proc.tail(result.stderr, 800)),
            "workspace": summary.get("workspace") or (str(workspaces[0]) if workspaces else ""),
            "duration_s": result.duration_s, "cost_usd": usage.get("cost_usd", 0.0),
            "agent_calls": usage.get("calls", 0), "timed_out": result.timed_out,
            "stories": summary.get("stories", [])}


def run_harness(brief: Brief, run_dir: Path, cap_s: float, model: str) -> dict:
    """Config B: the bare harness. Same scaffold, same confinement, one session, no method."""
    from autospec.core.agent import ClaudeCodeRunner
    from autospec.core.models import Profile
    from autospec.core.ports import AgentCall, AgentError, Capability
    from autospec.core.profiles import scaffold
    from autospec.core.prompts import SYSTEM
    from autospec.core.settings import Settings

    ws = run_dir / brief.package.replace("_", "-")
    ws.mkdir()
    started = time.monotonic()
    scaffold(ws, project_name=brief.name, package=brief.package, profile=Profile(brief.profile))
    prompt = (f"{brief.body}\n\nImplement this whole product in this repository (package `{brief.package}`). "
              "Work in TDD, run `uv run pytest` until the whole suite is green, declare every dependency "
              "with `uv add`. When done, answer with a one-paragraph summary.")
    system = SYSTEM["dev"].split("\n", 1)[1] if "\n" in SYSTEM["dev"] else ""
    call = AgentCall(role="dev", prompt=prompt, system_prompt=f"{HARNESS_SYSTEM}\n{system}",
                     capability=Capability.DEV, cwd=ws, model=model, timeout_s=cap_s, max_budget_usd=30)
    try:
        result = asyncio.run(ClaudeCodeRunner(Settings(model=model)).arun(call))
        completed, error, cost, calls = True, "", result.cost_usd, 1
    except AgentError as exc:
        completed, error = False, f"{exc.kind}: {exc}"
        cost, calls = (exc.result.cost_usd if exc.result else 0.0), 1
    return {"completed": completed, "phase": "done" if completed else "error", "error": error,
            "workspace": str(ws), "duration_s": round(time.monotonic() - started, 1), "cost_usd": cost,
            "agent_calls": calls, "timed_out": "timeout" in error}


def run_v1(brief: Brief, run_dir: Path, cap_s: float, model: str) -> dict:
    """Config A: the v1 factory, production .env, every model forced to the bench model."""
    import os

    from bench.v1_driver import MODEL_VARS

    brief_file = run_dir / "brief.md"
    brief_file.write_text(brief.body, encoding="utf-8")
    out = run_dir / "v1-summary.json"
    env = {**os.environ, **{name: model for name in MODEL_VARS}}
    env.pop("VIRTUAL_ENV", None)
    argv = [sys.executable, "-m", "bench.v1_driver", "--name", brief.name, "--package", brief.package,
            "--goal", brief.goal, "--brief-file", str(brief_file), "--workspace-root", str(run_dir / "ws"),
            "--cap-s", str(cap_s), "--out", str(out)]
    # The driver's own cap disposes the pipeline cleanly; the outer cap is the safety net.
    result = proc.run(argv, cwd=BACKEND_DIR, env=env, timeout_s=cap_s + 300,
                      stdout_path=run_dir / "factory.stdout", stderr_path=run_dir / "factory.stderr")
    if out.is_file():
        return json.loads(out.read_text(encoding="utf-8"))
    workspaces = [p for p in (run_dir / "ws").glob("*") if p.is_dir()]
    return {"completed": False, "phase": "crashed", "error": proc.tail(result.stderr, 1500),
            "timed_out": result.timed_out, "workspace": str(workspaces[0]) if workspaces else "",
            "duration_s": result.duration_s, "cost_usd": None, "agent_calls": None}


CONFIGS = {"a": run_v1, "b": run_harness, "c": run_v2}


def _result_path(day: str, config: str, project: str) -> Path:
    folder = DOCS_BENCH_DIR / day / config
    folder.mkdir(parents=True, exist_ok=True)
    i = 1
    while (folder / f"{project}-{i}.json").exists():
        i += 1
    return folder / f"{project}-{i}.json"


def record(day: str, config: str, brief: Brief, model: str, factory: dict) -> Path:
    report = judge(brief.id, Path(factory["workspace"]), brief.package, brief.profile) \
        if factory.get("workspace") and Path(factory["workspace"]).is_dir() else None
    result = {
        "date": day, "config": config, "project": brief.id, "model": model, "git_sha": _git_sha(),
        "brief_sha256": brief.sha256, "bench_version": brief.bench_version,
        "m1_completed": factory.get("completed", False), "m2_duration_s": factory.get("duration_s"),
        "m3_cost_usd": factory.get("cost_usd"), "m4_agent_calls": factory.get("agent_calls"),
        "m8_interventions": 0, "factory": factory, "oracle": report,
    }
    path = _result_path(day, config, brief.id)
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m bench.run")
    parser.add_argument("--config", default="c")
    parser.add_argument("--project", required=True)
    parser.add_argument("--n", type=int, default=1)
    parser.add_argument("--model", default="sonnet")
    parser.add_argument("--cap-s", type=float, default=2400)
    parser.add_argument("--date", default=date.today().isoformat())
    parser.add_argument("--oracle-only", action="store_true")
    parser.add_argument("--workspace", type=Path)
    args = parser.parse_args(argv)
    brief = load_brief(args.project)

    if args.oracle_only:
        factory = {"completed": None, "workspace": str(args.workspace.resolve())}
        path = record(args.date, args.config, brief, args.model, factory)
        print(path.read_text(encoding="utf-8"))
        return 0

    for _ in range(args.n):
        run_dir = WORKSPACE_BENCH_DIR / args.date / args.config / f"{args.project}-{time.strftime('%H%M%S')}"
        run_dir.mkdir(parents=True)
        factory = CONFIGS[args.config](brief, run_dir, args.cap_s, args.model)
        path = record(args.date, args.config, brief, args.model, factory)
        data = json.loads(path.read_text(encoding="utf-8"))
        oracle = data["oracle"] or {}
        print(json.dumps({"result": str(path), "m1": data["m1_completed"], "m2_s": data["m2_duration_s"],
                          "m3_usd": data["m3_cost_usd"], "m6": (oracle.get("m6_oracle") or {}).get("rate"),
                          "m5": (oracle.get("m5_suite") or {}).get("green"),
                          "m7": (oracle.get("m7_smoke") or {}).get("ok")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
