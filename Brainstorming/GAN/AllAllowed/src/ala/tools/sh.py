"""The ``sh`` tool (W4): run one virtual shell command through the shell module.

This is a thin wrapper. The shell (W3) does all the work and owns the closed command set; the tool
just adapts its ``ShellResult`` to a ``ToolResult`` so the resolver handles every tool uniformly.
"""

from __future__ import annotations

import random
from collections.abc import Mapping

from ala.kernel import Kernel
from ala.shell import run_shell
from ala.tools.result import ToolResult
from ala.types import AgentId


def apply_sh(kernel: Kernel, actor: AgentId, args: Mapping[str, str], rng: random.Random) -> ToolResult:
    result = run_shell(kernel, actor, args.get("cmd", ""))
    return ToolResult(
        ok=result.ok,
        stdout=result.stdout,
        effects=result.effects,
        error=None if result.ok else result.stdout,
    )
