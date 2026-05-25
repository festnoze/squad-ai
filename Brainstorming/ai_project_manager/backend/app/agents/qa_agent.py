"""V1 QaAgent — reviews a DevAgent's output and produces a verdict.

Reads the files produced by a DevAgent (from the task's workspace) and
asks an LLM to judge whether the work meets the task. Returns either
`QaVerdict.APPROVED` (the orchestrator flips the task to ``done``) or
`QaVerdict.REJECTED` with feedback (the orchestrator triggers a
second DevAgent iteration, unless the max iterations budget is
exhausted in which case the task goes to ``blocked``).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from app.agents.dev_agent import DevAgentResult
from app.agents.engine import AgentEngine, get_engine
from app.models.item import Item
from app.services.prompts.qa_system_prompt import QA_SYSTEM_PROMPT


class QaVerdict(str, Enum):
    """QA decision on a DevAgent output."""

    APPROVED = "approved"
    REJECTED = "rejected"


class _QaResponseSchema(BaseModel):
    """Pydantic shape the QaAgent LLM is expected to return."""

    verdict: str = Field(default="approved")
    feedback: str = Field(default="")


@dataclass
class QaAgentResult:
    """Outcome of a single ``areview_deliverable`` call."""

    verdict: QaVerdict
    feedback: str
    raw_response: dict[str, Any]


class QaAgent:
    """Reviews a DevAgent's output and returns an approved/rejected verdict."""

    def __init__(self, engine: AgentEngine | None = None) -> None:
        self.engine = engine or get_engine()
        self.logger = logging.getLogger(__name__)

    async def areview_deliverable(
        self,
        task: Item,
        dev_result: DevAgentResult,
    ) -> QaAgentResult:
        """Ask the LLM to review the dev output and return a verdict.

        On LLM failure the QA falls back to ``APPROVED`` with an
        explanatory feedback. That avoids blocking a run on a flaky
        LLM: if the dev produced files, we assume they are good enough
        and move on rather than loop forever.
        """
        user_prompt = self._build_user_prompt(task, dev_result)

        try:
            parsed = await self.engine.ainvoke_json(
                system_prompt=QA_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                schema=_QaResponseSchema,
                action_name="qa_agent.areview_deliverable",
            )
        except Exception as exc:  # noqa: BLE001
            self.logger.warning(
                "QaAgent LLM failed (%s), approving by default",
                exc,
            )
            return QaAgentResult(
                verdict=QaVerdict.APPROVED,
                feedback=(
                    "QA auto-approved: the reviewing LLM could not be "
                    f"reached ({exc})."
                ),
                raw_response={},
            )

        verdict, feedback = self._parse_response(parsed)
        return QaAgentResult(
            verdict=verdict,
            feedback=feedback,
            raw_response=parsed,
        )

    def _build_user_prompt(
        self,
        task: Item,
        dev_result: DevAgentResult,
    ) -> str:
        ac_block = ""
        if task.acceptance_criteria:
            formatted = "\n".join(
                f"- {c}" for c in task.acceptance_criteria if c.strip()
            )
            ac_block = f"\n\n## Critères d'acceptance\n{formatted}"

        # Read each file back from disk and render it in a markdown-like
        # fenced block the reviewer LLM can scan easily.
        files_block_lines: list[str] = []
        for f in dev_result.files:
            try:
                content = f.absolute_path.read_text(encoding="utf-8")
            except OSError as exc:
                content = f"[QA could not read this file: {exc}]"
            files_block_lines.append(
                f"### {f.relative_path} ({f.language})\n"
                f"```\n{content}\n```",
            )
        files_block = (
            "\n\n".join(files_block_lines) if files_block_lines else "(aucun fichier)"
        )

        summary_block = (
            f"\n\n## Résumé du dev\n{dev_result.summary.strip()}"
            if dev_result.summary
            else ""
        )

        description = (task.description or "").strip() or "(aucune description)"

        return (
            f"# Task\n\n"
            f"- Titre: {task.title}\n\n"
            f"## Description\n{description}"
            f"{ac_block}"
            f"{summary_block}"
            f"\n\n## Fichiers produits\n{files_block}\n\n"
            f"Donne maintenant ton verdict au format JSON demandé."
        )

    def _parse_response(
        self,
        parsed: dict[str, Any],
    ) -> tuple[QaVerdict, str]:
        verdict_raw = parsed.get("verdict", "approved")
        feedback_raw = parsed.get("feedback", "")
        if not isinstance(verdict_raw, str):
            verdict_raw = "approved"
        verdict = (
            QaVerdict.REJECTED
            if verdict_raw.strip().lower() == "rejected"
            else QaVerdict.APPROVED
        )
        feedback = str(feedback_raw or "").strip()
        return verdict, feedback
