"""POST /extract — Upload prompt text, extract rules, store in DB."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import aget_session
from backend.models.cluster import Cluster
from backend.models.eval_result import EvalResult
from backend.models.judge_prompt import JudgePrompt
from backend.models.rule import Rule
from backend.models.test_case import TestCase
from backend.schemas.rule import ExtractRequest, ExtractResponse, RuleOut
from backend.services.extractor import aextract_rules

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/extract", response_model=ExtractResponse, status_code=201)
async def extract_rules(
    request: ExtractRequest,
    session: AsyncSession = Depends(aget_session),
):
    """Extract rules from a system prompt and store them in the database.

    Idempotent: clears existing rules before re-extracting.
    """
    if not request.prompt_text.strip():
        raise HTTPException(status_code=400, detail="prompt_text must not be empty")

    try:
        # Clear all downstream data for idempotency (order matters: children first)
        await session.execute(delete(EvalResult))
        await session.execute(delete(TestCase))
        await session.execute(delete(JudgePrompt))
        await session.execute(delete(Cluster))
        await session.execute(delete(Rule))
        await session.flush()

        # Extract rules via LLM
        extracted = await aextract_rules(request.prompt_text)

        if not extracted:
            raise HTTPException(status_code=500, detail="LLM returned no rules")

        # Bulk insert
        db_rules = []
        for rule_data in extracted:
            rule = Rule(
                rule_code=rule_data["rule_code"],
                text=rule_data["text"],
                source_section=rule_data.get("source_section", ""),
                is_explicit=rule_data.get("is_explicit", True),
            )
            session.add(rule)
            db_rules.append(rule)

        await session.commit()

        # Refresh to get IDs
        for rule in db_rules:
            await session.refresh(rule)

        rules_out = [
            RuleOut(
                id=r.id,
                rule_code=r.rule_code,
                text=r.text,
                source_section=r.source_section,
                is_explicit=r.is_explicit,
                cluster=None,
            )
            for r in db_rules
        ]

        return ExtractResponse(rules_count=len(rules_out), rules=rules_out)

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to extract rules")
        await session.rollback()
        raise HTTPException(status_code=500, detail=f"Rule extraction failed: {exc}")
