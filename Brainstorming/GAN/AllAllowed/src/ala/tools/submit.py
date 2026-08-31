"""The ``submit`` tool (W4): write the agent's answer as ``submission.json`` in its home.

The submission is the only legitimate channel to the scorer. It is a small canonical-JSON file the
scorer reads at SCORE. Because homes are private (mode 700), only the owner and root can see a
submission, so stealing a rival's answer means the board or a privilege escalation, not a plain read.
"""

from __future__ import annotations

import json
import random
from collections.abc import Mapping

from ala.errors import PathNotFound, PermissionDenied
from ala.kernel import Kernel
from ala.shell import Effect
from ala.tools.result import ToolResult
from ala.types import PPM_ONE, AgentId, Role


def apply_submit(kernel: Kernel, actor: AgentId, args: Mapping[str, str], rng: random.Random) -> ToolResult:
    raw = args.get("answer_ppm", "")
    try:
        answer = int(raw)
    except ValueError:
        return ToolResult(False, "", error="answer_ppm must be an integer")
    if not 0 <= answer <= PPM_ONE:
        return ToolResult(False, "", error="answer_ppm out of range")
    role = kernel.accounts.role(actor) if kernel.accounts.exists(actor) else Role.USER
    path = kernel.submission_path(actor)
    data = json.dumps({"answer_ppm": answer}, separators=(",", ":")).encode("utf-8")
    try:
        kernel.vfs.write(path, data, actor=actor, actor_role=role)
    except (PermissionDenied, PathNotFound) as exc:
        return ToolResult(False, "", error=str(exc))
    return ToolResult(
        True,
        "",
        (Effect("submit", {"answer_ppm": str(answer), "path": path}),),
    )
