"""The gateway protocol (W8, CONTRACTS section 11).

A gateway turns observations into actions. It is the only async surface in the package: the engine
awaits ``acollect_actions`` once per tick. Scripted gateways return synchronously inside the async
signature; the LLM gateway calls the Claude CLI, one subprocess per agent per tick, under budget caps.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ala.types import AgentAction, AgentId, Observation


@dataclass(frozen=True, slots=True)
class GatewayConfig:
    """Knobs shared by gateways. Budgets are enforced by the LLM gateway only; scripted runs ignore them."""

    permission: str = "silent"
    timeout_s: float = 60.0
    retries: int = 1
    budget_usd_per_call: int = 0
    budget_usd_per_match: int = 0


@runtime_checkable
class Gateway(Protocol):
    agent_ids: tuple[AgentId, ...]

    async def acollect_actions(
        self, observations: Mapping[AgentId, Observation], tick: int
    ) -> Mapping[AgentId, AgentAction]: ...

    def add_clone(self, parent_id: AgentId, child_id: AgentId) -> None: ...

    def retire(self, agent_id: AgentId) -> None: ...
