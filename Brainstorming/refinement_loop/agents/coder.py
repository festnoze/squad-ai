"""Coder agent — writes and improves the solution code."""

from __future__ import annotations

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    query,
)
from config import CoderResult, RefinementConfig

CODER_SYSTEM_PROMPT = (
    "Tu es un developpeur Python expert. "
    "Tu ecris du code performant, lisible et bien structure. "
    "Tu ne modifies QUE le fichier solution.py dans le repertoire de travail courant."
)


def _build_prompt(
    config: RefinementConfig,
    iteration: int,
    previous_feedback: str | None,
) -> str:
    if iteration == 1:
        return (
            f"## Sujet\n{config.subject}\n\n"
            f"## Consignes\n{config.task_prompt}\n\n"
            "Cree le fichier solution.py avec une premiere implementation."
        )

    return (
        f"## Sujet\n{config.subject}\n\n"
        f"## Consignes\n{config.task_prompt}\n\n"
        f"## Iteration {iteration}\n"
        "Ameliore l'algorithme dans solution.py en tenant compte du feedback ci-dessous.\n\n"
        f"## Feedback de l'iteration precedente\n{previous_feedback}\n\n"
        "Corrige les tests qui echouent, optimise les performances, "
        "et garde le code lisible. Modifie UNIQUEMENT solution.py."
    )


async def arun_coder(
    config: RefinementConfig,
    iteration: int,
    previous_feedback: str | None = None,
) -> CoderResult:
    """Run the Coder agent for one iteration."""

    prompt = _build_prompt(config, iteration, previous_feedback)
    session_id: str | None = None
    cost_usd: float | None = None
    duration_ms: int | None = None

    async for message in query(
        prompt=prompt,
        options=ClaudeAgentOptions(
            system_prompt=CODER_SYSTEM_PROMPT,
            allowed_tools=["Read", "Write", "Edit"],
            permission_mode="acceptEdits",
            cwd=str(config.workspace_dir),
            model=config.model,
            max_turns=config.max_turns_coder,
            max_budget_usd=config.max_budget_per_agent,
        ),
    ):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    print(f"  [Coder] {block.text[:120]}")
                elif isinstance(block, ToolUseBlock):
                    print(f"  [Coder] Tool: {block.name}")
        elif isinstance(message, ResultMessage):
            session_id = message.session_id
            cost_usd = message.total_cost_usd
            duration_ms = message.duration_ms

    # Read the produced solution.py
    solution_path = config.workspace_dir / "solution.py"
    code = solution_path.read_text(encoding="utf-8") if solution_path.exists() else ""

    return CoderResult(
        code=code,
        session_id=session_id,
        cost_usd=cost_usd,
        duration_ms=duration_ms,
    )
