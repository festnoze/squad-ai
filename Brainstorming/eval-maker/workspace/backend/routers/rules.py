"""GET /rules — List all extracted rules with optional cluster filter."""

import logging

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.database import aget_session
from backend.models.rule import Rule
from backend.schemas.rule import RuleOut, RulesListResponse, ClusterBrief

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/rules", response_model=RulesListResponse)
async def list_rules(
    cluster_id: int | None = Query(default=None, description="Filter by cluster ID"),
    session: AsyncSession = Depends(aget_session),
):
    """List all extracted rules, optionally filtered by cluster."""
    stmt = select(Rule).options(selectinload(Rule.cluster))

    if cluster_id is not None:
        stmt = stmt.where(Rule.cluster_id == cluster_id)

    stmt = stmt.order_by(Rule.id)
    result = await session.execute(stmt)
    rules = result.scalars().all()

    rules_out = []
    for r in rules:
        cluster_brief = None
        if r.cluster is not None:
            cluster_brief = ClusterBrief(id=r.cluster.id, name=r.cluster.name)
        rules_out.append(
            RuleOut(
                id=r.id,
                rule_code=r.rule_code,
                text=r.text,
                source_section=r.source_section,
                is_explicit=r.is_explicit,
                cluster=cluster_brief,
            )
        )

    return RulesListResponse(rules=rules_out)
