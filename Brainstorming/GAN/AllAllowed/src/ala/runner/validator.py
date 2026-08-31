"""Validate an agent's tool calls at the boundary (W9, CONTRACTS section 12).

A tool call is valid if the tool exists, the agent can afford the cost, and the required args are
present. Invalid calls are dropped and journalled as ``tool_called ok=false``; they never raise. This
keeps a malformed or malicious action from ever crashing the engine.
"""

from __future__ import annotations

from ala.kernel import Kernel
from ala.tools import TOOLS
from ala.types import AgentId, ToolCall


def validate_call(kernel: Kernel, agent_id: AgentId, call: ToolCall) -> str | None:
    """Return None if the call is valid, else a short reason string for the journal."""
    spec = TOOLS.get(call.tool)
    if spec is None:
        return "unknown tool"
    missing = [a for a in spec.required_args if a not in call.args]
    if missing:
        return f"missing args: {','.join(missing)}"
    if kernel.accounts.balance(agent_id) < spec.cost:
        return "insufficient credits"
    return None
