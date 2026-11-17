"""Config A: the v1 factory as it is on `main`, driven headless (mirrors scripts/build_driver.py).

Always launched by bench.run in a SUBPROCESS: v1 loads backend/.env into module
globals at import time, which must never leak into the bench process. Every model
variable is forced to the bench model for parity; the rest of the production .env
is left untouched.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path

MODEL_VARS = ("CLAUDE_MODEL", "MODEL_BOSS", "MODEL_WORKER", "MODEL_CHECKER", "CONSTITUTION_MODEL",
              "MODEL_SPEC", "MODEL_ANALYZE", "MODEL_PLAN", "MODEL_ARCHITECT", "MODEL_BUILD", "MODEL_DONE",
              "MODEL_LADDER", "ANTHROPIC_MODEL")


def _last_failure(ws: Path) -> str:
    """v1 often parks with an empty error: the reason is the last failure line of its monitor."""
    monitor = ws / "build-monitor.jsonl"
    if not monitor.is_file():
        return ""
    reason = ""
    for line in monitor.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        text = str(event.get("line", ""))
        if "❌" in text or "ERROR" in text or "FAIL" in text:
            reason = text
    return reason[-1500:]


async def _arun(args) -> dict:
    from autospec.config import settings

    settings.agent_provider = "claude code"
    settings.fake_agents = False
    settings.approval_gates_enabled = False
    settings.brainstorm_assist_enabled = False
    settings.workspace_root = args.workspace_root

    from autospec.agents.providers import make_runner
    from autospec.models import ChatMessage, ChatRole, ProjectState, new_id
    from autospec.orchestrator.pipeline import Pipeline
    from autospec.storage import workspace_dir

    brief = args.brief_file.read_text(encoding="utf-8")
    state = ProjectState(id=new_id(args.package.replace("_", "-")), name=args.name, goal=args.goal,
                         auto_spec=False, brief=brief)
    state.chat.append(ChatMessage(role=ChatRole.USER, content=args.goal))
    pipeline = Pipeline(state, make_runner("claude code"))
    started = time.monotonic()
    timed_out = False
    try:
        await asyncio.wait_for(pipeline._alifecycle(), timeout=args.cap_s)
    except asyncio.TimeoutError:
        timed_out = True
        await pipeline.adispose()
    ws = workspace_dir(state.id)
    return {
        "completed": state.phase.value == "done" and not timed_out,
        "phase": state.phase.value, "error": str(state.error or "")[-1500:] or _last_failure(ws),
        "timed_out": timed_out, "workspace": str(ws), "duration_s": round(time.monotonic() - started, 1),
        "cost_usd": round(state.usage.cost_usd, 4), "agent_calls": state.usage.agent_calls,
        "stories": [{"id": s.id, "status": s.status.value, "attempts": s.attempts} for s in state.stories],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--package", required=True)
    parser.add_argument("--goal", required=True)
    parser.add_argument("--brief-file", type=Path, required=True)
    parser.add_argument("--workspace-root", type=Path, required=True)
    parser.add_argument("--cap-s", type=float, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    summary = asyncio.run(_arun(args))
    args.out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
