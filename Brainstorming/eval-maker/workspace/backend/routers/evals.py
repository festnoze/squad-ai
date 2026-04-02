"""POST /run-evals — Execute evaluations: system call + judge scoring."""

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.database import aget_session
from backend.models.cluster import Cluster
from backend.models.eval_result import EvalResult
from backend.models.judge_prompt import JudgePrompt
from backend.models.rule import Rule
from backend.models.test_case import TestCase
from backend.schemas.eval_result import RunEvalsRequest, RunEvalsResponse
from backend.services.eval_runner import arun_evals_batch

logger = logging.getLogger(__name__)
router = APIRouter()

# Load the SkillForge prompt for the system under test
_PROMPT_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "skillforge-prompt.txt"


def _load_system_prompt() -> str:
    """Load the SkillForge system prompt from disk."""
    if _PROMPT_PATH.exists():
        return _PROMPT_PATH.read_text(encoding="utf-8")
    # Fallback: try the input path
    fallback = Path(__file__).resolve().parent.parent.parent.parent / "input" / "skillforge-prompt.txt"
    if fallback.exists():
        return fallback.read_text(encoding="utf-8")
    return ""


@router.post("/run-evals", response_model=RunEvalsResponse)
async def run_evals(
    request: RunEvalsRequest | None = None,
    session: AsyncSession = Depends(aget_session),
):
    """Execute evaluations for test cases."""
    if request is None:
        request = RunEvalsRequest()

    system_prompt = _load_system_prompt()
    if not system_prompt:
        raise HTTPException(
            status_code=500,
            detail="SkillForge system prompt not found at data/skillforge-prompt.txt",
        )

    # Fetch test cases
    stmt = select(TestCase).order_by(TestCase.id)
    if request.test_case_ids:
        stmt = stmt.where(TestCase.id.in_(request.test_case_ids))
    result = await session.execute(stmt)
    test_cases = result.scalars().all()

    if not test_cases:
        raise HTTPException(status_code=404, detail="No test cases found.")

    # Fetch rules to build rule_id -> cluster_id mapping
    result = await session.execute(select(Rule))
    rules = result.scalars().all()
    rule_to_cluster = {r.id: r.cluster_id for r in rules if r.cluster_id is not None}

    # Fetch judge prompts by cluster
    result = await session.execute(select(JudgePrompt))
    judge_prompts_list = result.scalars().all()

    if not judge_prompts_list:
        raise HTTPException(status_code=404, detail="No judge prompts found. Run /generate-judges first.")

    judge_prompts_by_cluster = {
        jp.cluster_id: {
            "system_prompt": jp.system_prompt,
            "rubric_json": jp.rubric_json,
        }
        for jp in judge_prompts_list
    }

    # Build test case dicts
    tc_dicts = [
        {
            "id": tc.id,
            "rule_ids": tc.rule_ids or [],
            "scenario_type": tc.scenario_type,
            "user_input": tc.user_input,
            "expected_behavior": tc.expected_behavior,
            "tags": tc.tags or [],
        }
        for tc in test_cases
    ]

    try:
        eval_results = await arun_evals_batch(
            test_cases=tc_dicts,
            system_prompt=system_prompt,
            judge_prompts_by_cluster=judge_prompts_by_cluster,
            rule_to_cluster=rule_to_cluster,
            concurrency=request.concurrency,
        )
    except Exception as exc:
        logger.exception("Eval batch execution failed")
        raise HTTPException(status_code=500, detail=f"Eval execution failed: {exc}")

    # Build rule_code -> rule_id mapping
    code_to_id = {r.rule_code: r.id for r in rules}

    # Store results in DB
    total_score = 0
    count = 0
    for er in eval_results:
        # Resolve rule_id from rule_code if needed
        rule_id = er.get("rule_id")
        if isinstance(rule_id, str):
            rule_id = code_to_id.get(rule_id)
        if rule_id is None:
            continue

        db_result = EvalResult(
            test_case_id=er.get("test_case_id"),
            rule_id=rule_id,
            score=er.get("score", 3),
            reasoning=er.get("reasoning", ""),
            system_response=er.get("system_response", ""),
        )
        session.add(db_result)
        total_score += er.get("score", 3)
        count += 1

    await session.commit()

    avg_score = round(total_score / count, 2) if count > 0 else 0.0

    return RunEvalsResponse(
        results_count=count,
        average_score=avg_score,
        completed=True,
    )
