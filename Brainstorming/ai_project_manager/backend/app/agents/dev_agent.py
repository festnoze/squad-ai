"""V1 DevAgent — produces real code for a single task.

Delegates the heavy lifting to an `AgentEngine` (common-tools by
default) and writes the resulting files to a sandboxed workspace under
``backend/generated/<project_id>/<item_id>/``. The workspace is kept
**outside** the real `backend/app/` and `frontend/src/` trees so no
agent output can ever collide with the codebase you actually ship.

If the LLM rejects the task for any reason (failed JSON parsing,
empty file list, unusable content) the DevAgent raises a
`DevAgentFailure` exception that the orchestration service catches and
records as a failed step.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.agents.engine import AgentEngine, get_engine
from app.models.item import Item
from app.services.prompts.dev_system_prompt import DEV_SYSTEM_PROMPT


class DevAgentFailure(RuntimeError):
    """Raised when the DevAgent cannot produce a usable deliverable."""


# ---------------------------------------------------------------------------
# LLM schema + result dataclass
# ---------------------------------------------------------------------------


class _DevFileSchema(BaseModel):
    """One file entry in the LLM's JSON response."""

    path: str = Field(description="Relative file path under the task workspace.")
    language: str = Field(
        default="python",
        description="One of: python, tsx, ts, md, json.",
    )
    content: str = Field(description="Full file content, no diffs, no ellipsis.")


class _DevResponseSchema(BaseModel):
    """Top-level JSON shape the DevAgent LLM is expected to return."""

    summary: str = Field(default="")
    files: list[_DevFileSchema] = Field(default_factory=list)


@dataclass
class DevFileOutput:
    """A single file produced by the DevAgent (after disk persistence)."""

    absolute_path: Path
    relative_path: str
    language: str


@dataclass
class DevAgentResult:
    """Outcome of a single ``aproduce_deliverable`` call."""

    summary: str = ""
    files: list[DevFileOutput] = field(default_factory=list)
    raw_response: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


# Characters allowed in a file path component. Everything else is rewritten
# to "_" so a malicious or hallucinated LLM path cannot escape the workspace.
_SAFE_PATH_RE = re.compile(r"[^A-Za-z0-9._\-/]+")


class DevAgent:
    """Produces real code for a single task.

    Args:
        workspace_root: directory where every project's task workspaces
            are created. Defaults to ``<backend>/generated``. Override
            in tests to a throwaway tmp dir.
        engine: `AgentEngine` to use. Defaults to the module-level
            singleton returned by `app.agents.engine.get_engine()`.
    """

    def __init__(
        self,
        workspace_root: Path | None = None,
        engine: AgentEngine | None = None,
    ) -> None:
        self.workspace_root = workspace_root or _default_workspace_root()
        self.engine = engine or get_engine()
        self.logger = logging.getLogger(__name__)

    async def aproduce_deliverable(
        self,
        task: Item,
        qa_feedback: str | None = None,
    ) -> DevAgentResult:
        """Invoke the LLM to produce code for ``task``.

        Args:
            task: The task to implement. Must be a TASK (not epic/US).
            qa_feedback: Optional feedback from a previous QA rejection.
                When present, it's injected into the prompt so the
                DevAgent can correct its previous attempt.
        """
        if task.id is None:
            raise DevAgentFailure("Cannot run DevAgent on an unpersisted task.")

        user_prompt = self._build_user_prompt(task, qa_feedback)
        self.logger.info(
            "DevAgent: generating deliverable for task %s (%s)",
            task.id,
            task.title,
        )

        try:
            parsed = await self.engine.ainvoke_json(
                system_prompt=DEV_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                schema=_DevResponseSchema,
                action_name="dev_agent.aproduce_deliverable",
            )
        except Exception as exc:  # noqa: BLE001
            raise DevAgentFailure(
                f"LLM invocation failed: {exc}",
            ) from exc

        summary, files = self._parse_response(parsed)
        if not files:
            raise DevAgentFailure(
                "DevAgent returned no files — task cannot be delivered.",
            )

        # Persist each file to the sandbox workspace.
        stored_files = self._persist_files(
            project_id=task.project_id,
            item_id=task.id,
            files=files,
        )

        return DevAgentResult(
            summary=summary,
            files=stored_files,
            raw_response=parsed,
        )

    # ------------------------------------------------------------------
    # Prompt building
    # ------------------------------------------------------------------

    def _build_user_prompt(
        self,
        task: Item,
        qa_feedback: str | None,
    ) -> str:
        """Render a task into a compact user prompt for the DevAgent LLM."""
        ac_block = ""
        if task.acceptance_criteria:
            formatted = "\n".join(
                f"- {c}" for c in task.acceptance_criteria if c.strip()
            )
            ac_block = f"\n\n## Critères d'acceptance\n{formatted}"

        feedback_block = ""
        if qa_feedback:
            feedback_block = (
                "\n\n## Retour du relecteur (itération précédente)\n"
                f"{qa_feedback.strip()}\n\n"
                "Corrige les points soulevés et produis une nouvelle "
                "version complète des fichiers."
            )

        complexity = task.complexity.value if task.complexity else "inconnue"
        description = (task.description or "").strip() or "(aucune description)"

        return (
            f"# Task\n\n"
            f"- Titre: {task.title}\n"
            f"- Complexité: {complexity}\n\n"
            f"## Description\n{description}"
            f"{ac_block}"
            f"{feedback_block}\n\n"
            f"Produis maintenant les fichiers de code correspondants "
            f"au format JSON demandé."
        )

    # ------------------------------------------------------------------
    # Response parsing + safety
    # ------------------------------------------------------------------

    def _parse_response(
        self,
        parsed: dict[str, Any],
    ) -> tuple[str, list[_DevFileSchema]]:
        """Pull `summary` + `files` out of the LLM response, defensive."""
        summary = ""
        summary_raw = parsed.get("summary")
        if isinstance(summary_raw, str):
            summary = summary_raw.strip()

        raw_files = parsed.get("files", [])
        if not isinstance(raw_files, list):
            return summary, []

        files: list[_DevFileSchema] = []
        for entry in raw_files:
            if not isinstance(entry, dict):
                continue
            path = entry.get("path")
            content = entry.get("content")
            language = entry.get("language", "python")
            if not isinstance(path, str) or not isinstance(content, str):
                continue
            if not path.strip() or not content.strip():
                continue
            files.append(
                _DevFileSchema(
                    path=path.strip(),
                    language=str(language or "python").strip(),
                    content=content,
                ),
            )
        return summary, files

    def _persist_files(
        self,
        project_id: UUID,
        item_id: UUID,
        files: list[_DevFileSchema],
    ) -> list[DevFileOutput]:
        """Write each file inside the task's sandbox workspace."""
        task_dir = self.workspace_root / str(project_id) / str(item_id)
        task_dir.mkdir(parents=True, exist_ok=True)

        stored: list[DevFileOutput] = []
        for file in files:
            safe_rel_path = _sanitize_relative_path(file.path)
            abs_path = task_dir / safe_rel_path
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            abs_path.write_text(file.content, encoding="utf-8")
            stored.append(
                DevFileOutput(
                    absolute_path=abs_path,
                    relative_path=safe_rel_path,
                    language=file.language,
                ),
            )

        # Also drop a tiny manifest so humans can inspect what the agent
        # did without re-running the LLM.
        manifest_path = task_dir / "_manifest.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "files": [
                        {
                            "path": f.relative_path,
                            "language": f.language,
                        }
                        for f in stored
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        return stored


def _default_workspace_root() -> Path:
    """Return ``<backend>/generated`` as an absolute path.

    Resolved from this module's location (``.../app/agents/dev_agent.py``
    → go up 3 levels to reach the backend root).
    """
    return Path(__file__).resolve().parents[2] / "generated"


def _sanitize_relative_path(raw: str) -> str:
    """Strip dangerous characters + prevent path escapes.

    * Leading slashes → removed so nothing can become absolute.
    * ``..`` segments → removed entirely (we don't try to resolve them).
    * Every character outside ``[A-Za-z0-9._-/]`` → replaced with ``_``.
    * Empty result → fallback to ``unnamed.txt``.
    """
    path = raw.strip().lstrip("/\\")
    # Drop any ".." segment by splitting and filtering.
    parts = [p for p in re.split(r"[\\/]+", path) if p and p != ".." and p != "."]
    if not parts:
        return "unnamed.txt"
    safe_parts = [_SAFE_PATH_RE.sub("_", p) for p in parts]
    return "/".join(safe_parts)
