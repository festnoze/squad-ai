"""POST /generate-judges — Generate LLM-as-judge prompts per cluster."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.database import aget_session
from backend.models.cluster import Cluster
from backend.models.judge_prompt import JudgePrompt
from backend.schemas.judge_prompt import JudgeOut, JudgesResponse
from backend.services.judge_generator import agenerate_judge_prompt

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/generate-judges", response_model=JudgesResponse)
async def generate_judges(
    session: AsyncSession = Depends(aget_session),
):
    """Generate LLM-as-judge prompts for each cluster."""
    result = await session.execute(
        select(Cluster).options(selectinload(Cluster.rules)).order_by(Cluster.id)
    )
    clusters = result.scalars().all()

    if not clusters:
        raise HTTPException(status_code=404, detail="No clusters found. Run /cluster first.")

    judges_out = []

    for cluster in clusters:
        # Delete existing judge for this cluster if present (idempotent regeneration)
        existing_result = await session.execute(
            select(JudgePrompt).where(JudgePrompt.cluster_id == cluster.id)
        )
        existing_jp = existing_result.scalar_one_or_none()
        if existing_jp:
            await session.delete(existing_jp)
            await session.flush()

        rule_dicts = [
            {"rule_code": r.rule_code, "text": r.text, "id": r.id}
            for r in cluster.rules
        ]

        if not rule_dicts:
            logger.warning("Cluster '%s' has no rules, skipping judge generation", cluster.name)
            continue

        try:
            judge_data = await agenerate_judge_prompt(
                cluster_name=cluster.name,
                cluster_description=cluster.description or "",
                rules=rule_dicts,
            )
        except Exception as exc:
            logger.exception("Judge generation failed for cluster '%s'", cluster.name)
            raise HTTPException(
                status_code=500,
                detail=f"Judge generation failed for cluster '{cluster.name}': {exc}",
            )

        jp = JudgePrompt(
            cluster_id=cluster.id,
            system_prompt=judge_data["system_prompt"],
            rubric_json=judge_data["rubric_json"],
        )
        session.add(jp)
        await session.flush()
        await session.refresh(jp)

        judges_out.append(
            JudgeOut(
                id=jp.id,
                cluster_id=cluster.id,
                cluster_name=cluster.name,
                rubric_rules_count=len(judge_data["rubric_json"]),
            )
        )

    await session.commit()

    return JudgesResponse(judges=judges_out)
