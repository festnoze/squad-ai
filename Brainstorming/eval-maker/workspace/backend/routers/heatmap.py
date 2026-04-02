"""GET /heatmap — Return scenarios x rules score matrix as JSON."""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.database import aget_session
from backend.models.cluster import Cluster
from backend.models.eval_result import EvalResult
from backend.models.rule import Rule
from backend.models.test_case import TestCase
from backend.schemas.heatmap import (
    HeatmapCluster,
    HeatmapResponse,
    HeatmapRule,
    HeatmapScenario,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/heatmap", response_model=HeatmapResponse)
async def get_heatmap(
    session: AsyncSession = Depends(aget_session),
):
    """Return the scenarios x rules score matrix for heatmap visualization."""
    # Fetch all rules ordered by id
    result = await session.execute(
        select(Rule).options(selectinload(Rule.cluster)).order_by(Rule.id)
    )
    rules = result.scalars().all()

    # Fetch all test cases
    result = await session.execute(select(TestCase).order_by(TestCase.id))
    test_cases = result.scalars().all()

    # Fetch all eval results
    result = await session.execute(select(EvalResult))
    eval_results = result.scalars().all()

    # Fetch all clusters with their rules
    result = await session.execute(
        select(Cluster).options(selectinload(Cluster.rules)).order_by(Cluster.id)
    )
    clusters = result.scalars().all()

    # Build rule index: rule.id -> position in the rules list
    rule_ids = [r.id for r in rules]
    rule_id_to_idx = {rid: idx for idx, rid in enumerate(rule_ids)}

    # Build test case index: tc.id -> position in the test_cases list
    tc_ids = [tc.id for tc in test_cases]
    tc_id_to_idx = {tcid: idx for idx, tcid in enumerate(tc_ids)}

    # Build score lookup: (test_case_id, rule_id) -> score
    score_map: dict[tuple[int, int], int] = {}
    for er in eval_results:
        key = (er.test_case_id, er.rule_id)
        score_map[key] = er.score

    # Build matrix: matrix[scenario_idx][rule_idx] = score or None
    matrix: list[list[int | None]] = []
    for tc in test_cases:
        row: list[int | None] = []
        for rule in rules:
            score = score_map.get((tc.id, rule.id))
            row.append(score)
        matrix.append(row)

    # Build response objects
    rules_out = [
        HeatmapRule(
            id=r.id,
            rule_code=r.rule_code,
            text=r.text,
            cluster_name=r.cluster.name if r.cluster else None,
        )
        for r in rules
    ]

    scenarios_out = [
        HeatmapScenario(
            test_case_id=tc.id,
            scenario_type=tc.scenario_type,
            user_input_preview=tc.user_input[:100] if tc.user_input else "",
        )
        for tc in test_cases
    ]

    clusters_out = [
        HeatmapCluster(
            id=c.id,
            name=c.name,
            rule_ids=[r.id for r in c.rules],
        )
        for c in clusters
    ]

    return HeatmapResponse(
        rules=rules_out,
        scenarios=scenarios_out,
        matrix=matrix,
        clusters=clusters_out,
    )
