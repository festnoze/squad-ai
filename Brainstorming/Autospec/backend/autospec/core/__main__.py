"""Command line entry point: ``python -m autospec.core run|resume|serve`` (docs/v2/CONTRACTS.md 7, 9.1)."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
import uuid
from dataclasses import replace
from pathlib import Path

from .models import Phase, ProjectState, Profile
from .pipeline import Pipeline
from .settings import Settings
from .store import Store


def _runner(settings: Settings, package: str, fake: bool):
    if fake or settings.fake_agents:
        from .fake import demo_runner
        return demo_runner(package)
    from .agent import ClaudeCodeRunner
    return ClaudeCodeRunner(settings)


def _progress(record: dict) -> None:
    details = {k: v for k, v in record.items() if k not in ("ts", "type")}
    print(f"[{record['ts'][11:19]}] {record['type']} {json.dumps(details, ensure_ascii=False)[:300]}",
          file=sys.stderr, flush=True)


def summary(state: ProjectState, ws: Path, duration_s: float) -> dict:
    return {
        "id": state.id,
        "workspace": str(ws),
        "phase": state.phase.value,
        "profile": state.profile.value if state.profile else None,
        "stories": [{"id": s.id, "status": s.status.value, "attempts": s.attempts} for s in state.stories],
        "usage": state.usage.model_dump(),
        "error": state.error,
        "duration_s": round(duration_s, 1),
    }


async def _arun(state: ProjectState, ws: Path, settings: Settings, fake: bool) -> int:
    started = time.monotonic()
    Store(ws).save(state)
    pipeline = Pipeline(state, ws, _runner(settings, state.package, fake), settings, on_event=_progress)
    await pipeline.arun()
    print(json.dumps(summary(state, ws, time.monotonic() - started), ensure_ascii=False), flush=True)
    return 0 if state.phase == Phase.DONE else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m autospec.core")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="create a project and build it")
    run.add_argument("--name", required=True)
    run.add_argument("--package")
    run.add_argument("--profile", choices=[p.value for p in Profile])
    source = run.add_mutually_exclusive_group(required=True)
    source.add_argument("--brief-file", type=Path)
    source.add_argument("--goal")
    run.add_argument("--workspace-root", type=Path)
    run.add_argument("--model")
    run.add_argument("--fake", action="store_true", help="scripted agents, no LLM call")
    resume = sub.add_parser("resume", help="resume a project from its workspace")
    resume.add_argument("workspace", type=Path)
    resume.add_argument("--model")
    resume.add_argument("--fake", action="store_true")
    serve = sub.add_parser("serve", help="serve the HTTP API v2 and the built frontend_v2")
    serve.add_argument("--port", type=int, default=8400)
    serve.add_argument("--workspace-root", type=Path)
    serve.add_argument("--fake", action="store_true", help="scripted agents, no LLM call")
    args = parser.parse_args(argv)

    settings = Settings()
    if getattr(args, "model", None):  # serve has no --model: each project carries its own
        settings = replace(settings, model=args.model)

    if args.command == "serve":
        from .api import serve
        root = (args.workspace_root or settings.workspace_root).resolve()
        settings = replace(settings, workspace_root=root)
        return serve(settings, port=args.port,
                     runner_factory=lambda state: _runner(settings, state.package, args.fake))
    if args.command == "resume":
        ws = args.workspace.resolve()
        state = Store(ws).load()
        return asyncio.run(_arun(state, ws, settings, args.fake))

    from .profiles import package_name
    package = args.package or package_name(args.name)
    root = (args.workspace_root or settings.workspace_root).resolve()
    project_id = f"{package.replace('_', '-')}-{uuid.uuid4().hex[:8]}"
    ws = root / project_id
    ws.mkdir(parents=True)
    brief = args.brief_file.read_text(encoding="utf-8") if args.brief_file else ""
    state = ProjectState(id=project_id, name=args.name, package=package,
                         profile=Profile(args.profile) if args.profile else None,
                         goal=args.goal or "", brief=brief)
    return asyncio.run(_arun(state, ws, settings, args.fake))


if __name__ == "__main__":
    sys.exit(main())
