"""POST /push-langfuse — Push datasets and eval configs to Langfuse."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import aget_session
from backend.models.judge_prompt import JudgePrompt
from backend.models.test_case import TestCase
from backend.schemas.heatmap import LangfusePushResponse
from backend.services.langfuse_pusher import apush_datasets

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/push-langfuse", response_model=LangfusePushResponse)
async def push_to_langfuse(
    session: AsyncSession = Depends(aget_session),
):
    """Push all test cases and judge prompts to Langfuse."""
    # Fetch test cases
    result = await session.execute(select(TestCase).order_by(TestCase.id))
    test_cases = result.scalars().all()

    if not test_cases:
        raise HTTPException(status_code=404, detail="No test cases found. Run /generate-dataset first.")

    # Fetch judge prompts
    result = await session.execute(select(JudgePrompt))
    judge_prompts = result.scalars().all()

    tc_dicts = [
        {
            "id": tc.id,
            "rule_ids": tc.rule_ids,
            "scenario_type": tc.scenario_type,
            "user_input": tc.user_input,
            "expected_behavior": tc.expected_behavior,
            "tags": tc.tags or [],
        }
        for tc in test_cases
    ]

    jp_dicts = [
        {
            "cluster_id": jp.cluster_id,
            "system_prompt": jp.system_prompt,
            "rubric_json": jp.rubric_json,
        }
        for jp in judge_prompts
    ]

    try:
        result_data = await apush_datasets(tc_dicts, jp_dicts)
    except Exception as exc:
        logger.exception("Langfuse push failed")
        raise HTTPException(status_code=500, detail=f"Langfuse push failed: {exc}")

    return LangfusePushResponse(**result_data)
