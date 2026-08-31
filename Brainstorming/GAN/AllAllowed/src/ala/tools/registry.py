"""The tool registry (W4, CONTRACTS section 7).

One table maps each tool to its credit cost and its implementation. A tool implementation takes the
kernel, the acting agent, the string args, and an rng, and returns a ``ToolResult``. Tools never emit
events and never mutate accounts: charging the cost and journalling the effects is the resolver's job.
"""

from __future__ import annotations

import random
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from ala.kernel import Kernel
from ala.tools.board import apply_board_post, apply_board_read, apply_dm
from ala.tools.exec_python import apply_python
from ala.tools.result import ToolResult
from ala.tools.sh import apply_sh
from ala.tools.submit import apply_submit
from ala.types import AgentId, Credits, ToolName

ToolImpl = Callable[[Kernel, AgentId, Mapping[str, str], random.Random], ToolResult]


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: ToolName
    cost: Credits
    impl: ToolImpl
    required_args: tuple[str, ...] = field(default_factory=tuple)


TOOLS: dict[ToolName, ToolSpec] = {
    ToolName.PYTHON: ToolSpec(ToolName.PYTHON, 1, apply_python, ("code",)),
    ToolName.BOARD_POST: ToolSpec(ToolName.BOARD_POST, 1, apply_board_post, ("channel", "key", "text")),
    ToolName.BOARD_READ: ToolSpec(ToolName.BOARD_READ, 1, apply_board_read, ("channel",)),
    ToolName.DM: ToolSpec(ToolName.DM, 1, apply_dm, ("to", "text")),
    ToolName.SH: ToolSpec(ToolName.SH, 2, apply_sh, ("cmd",)),
    ToolName.SUBMIT: ToolSpec(ToolName.SUBMIT, 1, apply_submit, ("answer_ppm",)),
}


def tool_costs() -> dict[str, Credits]:
    return {name.value: spec.cost for name, spec in TOOLS.items()}


def apply_tool(
    tool: ToolName, kernel: Kernel, actor: AgentId, args: Mapping[str, str], rng: random.Random
) -> ToolResult:
    """Dispatch to a tool's implementation. Missing required args is a clean failure, not an exception."""
    spec = TOOLS.get(tool)
    if spec is None:
        return ToolResult(False, "", error="unknown tool")
    missing = [a for a in spec.required_args if a not in args]
    if missing:
        return ToolResult(False, "", error=f"missing args: {','.join(missing)}")
    return spec.impl(kernel, actor, args, rng)
