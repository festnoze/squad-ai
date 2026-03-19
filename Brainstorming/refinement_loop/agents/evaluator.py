"""Evaluator agent — writes tests, runs them, and produces structured feedback."""

from __future__ import annotations

import json

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    query,
)
from config import EVALUATOR_OUTPUT_SCHEMA, EvaluatorResult, RefinementConfig

EVALUATOR_SYSTEM_PROMPT = (
    "Tu es un ingenieur QA/test expert Python. "
    "Tu ecris des tests rigoureux avec pytest, tu les executes, "
    "et tu produis un rapport structure.\n"
    "Tu ne modifies QUE le fichier test_solution.py. "
    "Tu executes les tests via la commande pytest."
)


def _build_prompt(config: RefinementConfig, iteration: int) -> str:
    return (
        f"## Sujet\n{config.subject}\n\n"
        f"## Iteration {iteration}\n\n"
        f"## Exigences de test\n{config.test_requirements}\n\n"
        "## Instructions\n"
        "1. Lis le fichier solution.py pour comprendre le code actuel.\n"
        "2. Ecris (ou mets a jour) test_solution.py avec des tests pytest couvrant "
        "correction, performance et edge cases.\n"
        "3. Execute les tests avec : pytest test_solution.py -v\n"
        "4. Analyse les resultats et produis ton evaluation structuree.\n\n"
        "IMPORTANT : ta reponse finale doit etre un JSON conforme au schema demande."
    )


async def arun_evaluator(
    config: RefinementConfig,
    iteration: int,
) -> EvaluatorResult:
    """Run the Evaluator agent for one iteration."""

    prompt = _build_prompt(config, iteration)
    session_id: str | None = None
    cost_usd: float | None = None
    duration_ms: int | None = None
    structured_output: dict | None = None
    result_text: str = ""

    async for message in query(
        prompt=prompt,
        options=ClaudeAgentOptions(
            system_prompt=EVALUATOR_SYSTEM_PROMPT,
            allowed_tools=["Read", "Write", "Edit", "Bash"],
            permission_mode="acceptEdits",
            cwd=str(config.workspace_dir),
            model=config.model,
            max_turns=config.max_turns_evaluator,
            max_budget_usd=config.max_budget_per_agent,
            output_format={
                "type": "json_schema",
                "schema": EVALUATOR_OUTPUT_SCHEMA,
            },
        ),
    ):
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    print(f"  [Evaluator] {block.text[:120]}")
                elif isinstance(block, ToolUseBlock):
                    print(f"  [Evaluator] Tool: {block.name}")
        elif isinstance(message, ResultMessage):
            session_id = message.session_id
            cost_usd = message.total_cost_usd
            duration_ms = message.duration_ms
            structured_output = message.structured_output
            if message.result:
                result_text = message.result

    # Parse the structured output
    data = _parse_output(structured_output, result_text)

    return EvaluatorResult(
        tests_passed=data.get("tests_passed", 0),
        tests_failed=data.get("tests_failed", 0),
        test_output=data.get("test_output", ""),
        performance_metrics=data.get("performance_metrics", []),
        code_quality_issues=data.get("code_quality_issues", []),
        improvement_suggestions=data.get("improvement_suggestions", []),
        overall_assessment=data.get("overall_assessment", "No assessment produced."),
        should_continue=data.get("should_continue", True),
        session_id=session_id,
        cost_usd=cost_usd,
        duration_ms=duration_ms,
    )


def _parse_output(structured: dict | None, raw_text: str) -> dict:
    """Try structured_output first, then fall back to parsing raw text as JSON."""
    if structured and isinstance(structured, dict):
        return structured
    # Fallback: try to find JSON in the raw result text
    try:
        return json.loads(raw_text)
    except (json.JSONDecodeError, TypeError):
        pass
    # Last resort: return a minimal dict
    return {
        "tests_passed": 0,
        "tests_failed": 0,
        "test_output": raw_text or "Could not parse evaluator output.",
        "performance_metrics": [],
        "code_quality_issues": [],
        "improvement_suggestions": ["Could not parse structured output."],
        "overall_assessment": "Evaluator output could not be parsed.",
        "should_continue": True,
    }
