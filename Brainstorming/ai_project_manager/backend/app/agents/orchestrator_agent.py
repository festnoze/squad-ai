"""V1 OrchestratorAgent — picks which tasks to run next.

Unlike the DevAgent and QaAgent which drive real code generation, the
orchestrator is a **lightweight reasoning step**: given a list of
currently-executable tasks and a parallelism budget, it returns an
ordered subset to launch first. The rest of the orchestration (graph
walking, semaphore, dev/QA loop) lives in the
`app.application.project_run_service` module — the LLM is only
consulted for the "pick next batch" decision.

The agent gracefully degrades: if the LLM call fails or returns an
unusable payload, the orchestrator service falls back on a pure Python
scheduler that just picks tasks in insertion order, so a broken LLM can
never block the whole run.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.agents.engine import AgentEngine, get_engine
from app.models.item import Item
from app.services.prompts.orchestrator_system_prompt import (
    ORCHESTRATOR_SYSTEM_PROMPT,
)


class _OrchestratorSchema(BaseModel):
    """Pydantic shape the orchestrator LLM is expected to return."""

    selected_task_ids: list[str] = Field(default_factory=list)
    rationale: str = Field(default="")


@dataclass
class OrchestratorDecision:
    """Outcome of a single ``apick_next_batch`` call."""

    selected_task_ids: list[UUID] = field(default_factory=list)
    rationale: str = ""


class OrchestratorAgent:
    """Reasoning step that picks which tasks to launch next."""

    def __init__(self, engine: AgentEngine | None = None) -> None:
        self.engine = engine or get_engine()
        self.logger = logging.getLogger(__name__)

    async def apick_next_batch(
        self,
        executable_tasks: list[Item],
        max_parallel: int,
    ) -> OrchestratorDecision:
        """Ask the LLM which executable tasks to launch next.

        Always returns a valid decision — if the LLM call fails, the
        fallback is a plain "take the first N tasks" in insertion order.
        """
        if not executable_tasks or max_parallel <= 0:
            return OrchestratorDecision(selected_task_ids=[], rationale="")

        user_prompt = self._build_user_prompt(executable_tasks, max_parallel)

        try:
            parsed = await self.engine.ainvoke_json(
                system_prompt=ORCHESTRATOR_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                schema=_OrchestratorSchema,
                action_name="orchestrator_agent.apick_next_batch",
            )
        except Exception as exc:  # noqa: BLE001
            self.logger.warning(
                "Orchestrator LLM failed (%s), falling back to insertion order",
                exc,
            )
            return self._fallback_decision(executable_tasks, max_parallel)

        decision = self._parse_decision(parsed, executable_tasks, max_parallel)
        if not decision.selected_task_ids:
            return self._fallback_decision(executable_tasks, max_parallel)
        return decision

    def _build_user_prompt(
        self,
        executable_tasks: list[Item],
        max_parallel: int,
    ) -> str:
        """Describe the executable tasks in a compact JSON-ish format."""
        lines: list[str] = [
            f"max_parallel = {max_parallel}",
            "executable_tasks:",
        ]
        for task in executable_tasks:
            complexity = task.complexity.value if task.complexity else "unknown"
            description = (task.description or "").strip().replace("\n", " ")
            if len(description) > 200:
                description = description[:197] + "..."
            lines.append(
                f"- id={task.id} title={task.title!r} "
                f"complexity={complexity} description={description!r}",
            )
        return "\n".join(lines)

    def _parse_decision(
        self,
        parsed: dict[str, Any],
        executable_tasks: list[Item],
        max_parallel: int,
    ) -> OrchestratorDecision:
        """Turn the raw LLM dict into a validated `OrchestratorDecision`."""
        selected_raw = parsed.get("selected_task_ids", [])
        rationale_raw = parsed.get("rationale", "")
        if not isinstance(selected_raw, list):
            return OrchestratorDecision(rationale=str(rationale_raw or ""))

        known_uuids = {task.id for task in executable_tasks if task.id is not None}
        kept: list[UUID] = []
        for entry in selected_raw:
            if not isinstance(entry, str):
                continue
            try:
                uuid_value = UUID(entry)
            except (ValueError, TypeError):
                continue
            if uuid_value not in known_uuids:
                continue
            if uuid_value in kept:
                continue
            kept.append(uuid_value)
            if len(kept) >= max_parallel:
                break

        return OrchestratorDecision(
            selected_task_ids=kept,
            rationale=str(rationale_raw or ""),
        )

    def _fallback_decision(
        self,
        executable_tasks: list[Item],
        max_parallel: int,
    ) -> OrchestratorDecision:
        """Pure-Python fallback: first N tasks in insertion order."""
        kept: list[UUID] = []
        for task in executable_tasks:
            if task.id is None:
                continue
            kept.append(task.id)
            if len(kept) >= max_parallel:
                break
        return OrchestratorDecision(
            selected_task_ids=kept,
            rationale="Fallback: insertion order.",
        )
